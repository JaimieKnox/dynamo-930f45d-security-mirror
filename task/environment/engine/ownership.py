"""Ownership reconstruction helper for the fit smoke pipeline."""

from __future__ import annotations

from typing import Any

from . import shared


def _inc_id(slot: int, gen: int) -> str:
    return f"{slot}:{gen}"


def build_ownership(
    timeline: list[dict[str, Any]], objects: list[dict[str, Any]]
) -> dict[str, Any]:
    names: dict[str, set[str]] = {}
    shared.stream_scratch.clear()
    shared.path_claims.clear()

    def ensure(inc: str) -> None:
        names.setdefault(inc, set())

    def streams_for(slot: int, gen: int) -> dict[str, str]:
        return shared.stream_scratch.setdefault((slot, gen), {})

    for ev in timeline:
        slot = int(ev["slot"])
        gen = int(ev["gen"])
        inc = _inc_id(slot, gen)
        ensure(inc)
        kind = ev["kind"]
        bucket = streams_for(slot, gen)

        def claim(path: str | None) -> None:
            if not path:
                return
            prev = shared.path_claims.get(path)
            if prev is not None and prev != inc:
                names[prev].discard(path)
            shared.path_claims[path] = inc
            names[inc].add(path)

        def release(path: str | None) -> None:
            if not path:
                return
            names[inc].discard(path)
            if shared.path_claims.get(path) == inc:
                shared.path_claims.pop(path, None)

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

    # Publish incarnation-keyed stream scratch.
    streams: dict[str, dict[str, str]] = {}
    for inc in list(names.keys()):
        slot_s, gen_s = inc.split(":")
        streams[inc] = dict(
            shared.stream_scratch.get((int(slot_s), int(gen_s)), {})
        )

    journalled = {_inc_id(e["slot"], e["gen"]) for e in timeline}
    # Rebuild residual names from the object table after the journal pass.
    shared.path_claims.clear()
    for obj in objects:
        inc = _inc_id(int(obj["slot"]), int(obj["gen"]))
        if inc in journalled:
            ensure(inc)
            continue
        ensure(inc)
        for n in obj.get("names") or []:
            names[inc].add(n)
        for sname, digest in (obj.get("streams") or {}).items():
            streams.setdefault(inc, {})[sname] = digest

    incarnations = []
    for inc in sorted(names.keys(), key=lambda x: (int(x.split(":")[0]), int(x.split(":")[1]))):
        slot_s, gen_s = inc.split(":")
        incarnations.append(
            {
                "id": inc,
                "slot": int(slot_s),
                "gen": int(gen_s),
                "names": sorted(names[inc]),
                "streams": {k: streams.get(inc, {})[k] for k in sorted(streams.get(inc, {}).keys())},
            }
        )

    return {
        "incarnations": incarnations,
        "poisoned_paths": [],
    }
