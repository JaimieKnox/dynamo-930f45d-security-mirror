"""Ownership reconstruction for the shipped almost-correct engine.

Silent wrongs (shared-state / long-horizon):
streams accumulate in shared.streams_by_slot keyed by slot, not (slot, gen);
poison lives in shared.poison_paths and is cleared between journal and SI stages;
last-writer path map with no sticky poison during the journal pass.
"""

from __future__ import annotations

from typing import Any

from . import shared


def _inc_id(slot: int, gen: int) -> str:
    return f"{slot}:{gen}"


def build_ownership(
    timeline: list[dict[str, Any]], objects: list[dict[str, Any]]
) -> dict[str, Any]:
    names: dict[str, set[str]] = {}
    path_owner: dict[str, str] = {}
    shared.streams_by_slot.clear()
    shared.poison_paths.clear()

    def ensure(inc: str) -> None:
        names.setdefault(inc, set())

    def streams_for(slot: int) -> dict[str, str]:
        return shared.streams_by_slot.setdefault(slot, {})

    for ev in timeline:
        slot = int(ev["slot"])
        gen = int(ev["gen"])
        inc = _inc_id(slot, gen)
        ensure(inc)
        kind = ev["kind"]
        bucket = streams_for(slot)

        def claim(path: str | None) -> None:
            if not path:
                return
            prev = path_owner.get(path)
            if prev is not None and prev != inc:
                names[prev].discard(path)
                shared.poison_paths.add(path)
            path_owner[path] = inc
            names[inc].add(path)

        def release(path: str | None) -> None:
            if not path:
                return
            names[inc].discard(path)
            if path_owner.get(path) == inc:
                path_owner.pop(path, None)

        if kind == "CREATE":
            claim(ev.get("name"))
            stream = ev.get("stream") or "$DATA"
            content = ev.get("content")
            if content is not None:
                bucket[stream] = content
        elif kind == "LINK":
            claim(ev.get("name"))
        elif kind == "MOVE":
            release(ev.get("name_from"))
            claim(ev.get("name_to"))
        elif kind == "RENAME_NEW":
            claim(ev.get("name"))
        elif kind == "RENAME_OLD":
            release(ev.get("name"))
        elif kind == "DELETE":
            release(ev.get("name"))
        elif kind == "WRITE":
            stream = ev.get("stream") or "$DATA"
            content = ev.get("content")
            if content is not None:
                bucket[stream] = content
        elif kind == "CREATE_STREAM":
            stream = ev.get("stream")
            content = ev.get("content")
            if stream and content is not None:
                bucket[stream] = content
        elif kind == "DELETE_STREAM":
            stream = ev.get("stream")
            if stream:
                bucket.pop(stream, None)

    shared.poison_paths.clear()

    journalled = {_inc_id(e["slot"], e["gen"]) for e in timeline}
    all_incs = set(journalled)
    for obj in objects:
        all_incs.add(_inc_id(int(obj["slot"]), int(obj["gen"])))

    for obj in objects:
        slot = int(obj["slot"])
        gen = int(obj["gen"])
        inc = _inc_id(slot, gen)
        if inc in journalled:
            ensure(inc)
            continue
        ensure(inc)
        bucket = streams_for(slot)
        for n in obj.get("names") or []:
            names[inc].add(n)
        for sname, digest in (obj.get("streams") or {}).items():
            bucket[sname] = digest

    incarnations = []
    for inc in sorted(all_incs, key=lambda x: (int(x.split(":")[0]), int(x.split(":")[1]))):
        ensure(inc)
        slot_s, gen_s = inc.split(":")
        slot_i = int(slot_s)
        streams = dict(shared.streams_by_slot.get(slot_i, {}))
        incarnations.append(
            {
                "id": inc,
                "slot": slot_i,
                "gen": int(gen_s),
                "names": sorted(names[inc]),
                "streams": {k: streams[k] for k in sorted(streams.keys())},
            }
        )

    return {
        "incarnations": incarnations,
        "poisoned_paths": [],
    }
