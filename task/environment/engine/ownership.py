"""Ownership reconstruction helper used by the fit smoke pipeline."""

from __future__ import annotations

from typing import Any


def _inc_id(slot: int, gen: int) -> str:
    return f"{slot}:{gen}"


def build_ownership(
    timeline: list[dict[str, Any]], objects: list[dict[str, Any]]
) -> dict[str, Any]:
    names: dict[str, set[str]] = {}
    streams: dict[str, dict[str, str]] = {}
    path_owner: dict[str, str] = {}

    def ensure(inc: str) -> None:
        names.setdefault(inc, set())
        streams.setdefault(inc, {})

    for ev in timeline:
        inc = _inc_id(ev["slot"], ev["gen"])
        ensure(inc)
        kind = ev["kind"]

        def claim(path: str | None) -> None:
            if not path:
                return
            prev = path_owner.get(path)
            if prev is not None and prev != inc:
                names[prev].discard(path)
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
                streams[inc][stream] = content
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
                streams[inc][stream] = content
        elif kind == "CREATE_STREAM":
            stream = ev.get("stream")
            content = ev.get("content")
            if stream and content is not None:
                streams[inc][stream] = content
        elif kind == "DELETE_STREAM":
            stream = ev.get("stream")
            if stream:
                streams[inc].pop(stream, None)

    by_slot: dict[int, list[str]] = {}
    for inc in list(streams.keys()):
        slot = int(inc.split(":")[0])
        by_slot.setdefault(slot, []).append(inc)
    for _slot, incs in by_slot.items():
        incs_sorted = sorted(incs, key=lambda x: int(x.split(":")[1]))
        carried: dict[str, str] = {}
        for inc in incs_sorted:
            carried.update(streams.get(inc, {}))
            streams[inc] = dict(carried)

    journalled = {_inc_id(e["slot"], e["gen"]) for e in timeline}
    for obj in objects:
        inc = _inc_id(int(obj["slot"]), int(obj["gen"]))
        if inc in journalled:
            ensure(inc)
            continue
        ensure(inc)
        for n in obj.get("names") or []:
            names[inc].add(n)
        for sname, digest in (obj.get("streams") or {}).items():
            streams[inc][sname] = digest

    incarnations = []
    for inc in sorted(names.keys(), key=lambda x: (int(x.split(":")[0]), int(x.split(":")[1]))):
        slot_s, gen_s = inc.split(":")
        incarnations.append(
            {
                "id": inc,
                "slot": int(slot_s),
                "gen": int(gen_s),
                "names": sorted(names[inc]),
                "streams": {k: streams[inc][k] for k in sorted(streams.get(inc, {}).keys())},
            }
        )

    return {
        "incarnations": incarnations,
        "poisoned_paths": [],
    }
