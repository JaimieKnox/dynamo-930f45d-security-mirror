#!/usr/bin/env python3
"""Partial vault reconstruction helper shipped for fit smoke only.

This helper is intentionally incomplete. It is calibrated so fit/alpha smoke digests
pass while several CONTRACT rules remain wrong on held work packs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


OP_SEQ_MOD = 65536


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _inc_id(slot: int, gen: int) -> str:
    return f"{slot}:{gen}"


def _event_id(slot: int, gen: int, op_seq: int, kind: str) -> str:
    return f"{slot}:{gen}:{op_seq}:{kind}"


def _chronological_ops(
    oplog: list[dict[str, Any]], txnlog: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Oldest-first circular rotation. Silent wrong: drop ALL txnlog if any seq overlaps oplog."""
    if not oplog and not txnlog:
        return []

    by_seq: dict[int, dict[str, Any]] = {}
    for row in oplog:
        by_seq[int(row["op_seq"])] = dict(row)

    oplog_seqs = set(by_seq.keys())
    any_overlap = any(int(r["op_seq"]) in oplog_seqs for r in txnlog)
    # Silent wrong: if any txn seq duplicates oplog, ignore the entire txnlog.
    txn_only: list[dict[str, Any]] = []
    if not any_overlap:
        for row in txnlog:
            seq = int(row["op_seq"])
            if seq not in by_seq:
                txn_only.append(dict(row))

    if not by_seq and txn_only:
        return sorted(
            txn_only,
            key=lambda r: (int(r["wall"]), int(r["op_seq"]), int(r["slot"]), int(r["gen"])),
        )
    if not by_seq:
        return []

    oldest = min(
        by_seq.values(),
        key=lambda r: (int(r["wall"]), int(r["op_seq"]), int(r["slot"]), int(r["gen"])),
    )
    start = int(oldest["op_seq"])
    ordered_seqs = sorted(by_seq.keys(), key=lambda s: (s - start) % OP_SEQ_MOD)
    ordered: list[dict[str, Any]] = [by_seq[s] for s in ordered_seqs]

    if not txn_only:
        return ordered

    inserts = sorted(
        txn_only,
        key=lambda r: (
            (int(r["op_seq"]) - start) % OP_SEQ_MOD,
            int(r["wall"]),
            int(r["op_seq"]),
            int(r["slot"]),
            int(r["gen"]),
        ),
    )
    merged: list[dict[str, Any]] = []
    pending = list(inserts)
    for row in ordered:
        row_lin = (int(row["op_seq"]) - start) % OP_SEQ_MOD
        while pending and ((int(pending[0]["op_seq"]) - start) % OP_SEQ_MOD) <= row_lin:
            p = pending[0]
            p_lin = (int(p["op_seq"]) - start) % OP_SEQ_MOD
            if p_lin < row_lin or (
                p_lin == row_lin and int(p["wall"]) < int(row["wall"])
            ):
                merged.append(pending.pop(0))
            else:
                break
        merged.append(row)
    while pending:
        merged.append(pending.pop(0))
    return merged


def _coalesce(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Silent wrong: coalesce MOVE only when op_seq differs by exactly 1 mod 65536."""
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(ops):
        row = ops[i]
        if (
            row.get("kind") == "RENAME_OLD"
            and i + 1 < len(ops)
            and ops[i + 1].get("kind") == "RENAME_NEW"
            and int(ops[i + 1]["slot"]) == int(row["slot"])
            and int(ops[i + 1]["gen"]) == int(row["gen"])
            and (int(ops[i + 1]["op_seq"]) - int(row["op_seq"])) % OP_SEQ_MOD == 1
        ):
            new = ops[i + 1]
            out.append(
                {
                    "kind": "MOVE",
                    "slot": int(row["slot"]),
                    "gen": int(row["gen"]),
                    "op_seq": int(new["op_seq"]),
                    "wall": int(new["wall"]),
                    "name_from": row.get("name"),
                    "name_to": new.get("name"),
                    "stream": None,
                    "content": None,
                    "name": None,
                }
            )
            i += 2
            continue
        out.append(
            {
                "kind": row["kind"],
                "slot": int(row["slot"]),
                "gen": int(row["gen"]),
                "op_seq": int(row["op_seq"]),
                "wall": int(row["wall"]),
                "name": row.get("name"),
                "name_from": None,
                "name_to": None,
                "stream": row.get("stream"),
                "content": row.get("content"),
            }
        )
        i += 1
    return out


def reconstruct_case(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    objects = _load_jsonl(case_dir / "objects.jsonl")
    oplog = _load_jsonl(case_dir / "oplog.jsonl")
    txnlog = _load_jsonl(case_dir / "txnlog.jsonl")

    ordered = _chronological_ops(oplog, txnlog)
    events_raw = _coalesce(ordered)

    timeline: list[dict[str, Any]] = []
    for ev in events_raw:
        kind = ev["kind"]
        timeline.append(
            {
                "event_id": _event_id(ev["slot"], ev["gen"], ev["op_seq"], kind),
                "slot": ev["slot"],
                "gen": ev["gen"],
                "kind": kind,
                "time": ev["wall"],
                "op_seq": ev["op_seq"],
                "name": ev.get("name"),
                "name_from": ev.get("name_from"),
                "name_to": ev.get("name_to"),
                "stream": ev.get("stream"),
                "content": ev.get("content"),
            }
        )

    timeline.sort(key=lambda e: (e["time"], e["op_seq"], e["event_id"]))

    names: dict[str, set[str]] = {}
    streams: dict[str, dict[str, str]] = {}
    # Silent wrong: last-writer path map (no poison).
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

    # Silent wrong: inherit streams across gens in the same slot.
    by_slot: dict[int, list[str]] = {}
    for inc in list(streams.keys()):
        slot = int(inc.split(":")[0])
        by_slot.setdefault(slot, []).append(inc)
    for slot, incs in by_slot.items():
        incs_sorted = sorted(incs, key=lambda x: int(x.split(":")[1]))
        carried: dict[str, str] = {}
        for inc in incs_sorted:
            carried.update(streams.get(inc, {}))
            streams[inc] = dict(carried)

    # Silent wrong: skip SI-only zero-journal residuals from the object table.
    journalled = {_inc_id(e["slot"], e["gen"]) for e in timeline}
    for obj in objects:
        inc = _inc_id(int(obj["slot"]), int(obj["gen"]))
        if inc not in journalled:
            continue
        ensure(inc)

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

    ownership = {
        "incarnations": incarnations,
        "poisoned_paths": [],
    }
    return timeline, ownership


def dumps_timeline(timeline: list[dict[str, Any]]) -> str:
    return json.dumps(timeline, ensure_ascii=False, indent=2) + "\n"


def dumps_ownership(ownership: dict[str, Any]) -> str:
    return json.dumps(ownership, ensure_ascii=False, indent=2) + "\n"


def fit_smoke(fit_dir: Path) -> dict[str, str]:
    """Return sha256 digests of starter timeline/ownership JSON text for a fit pack."""
    timeline, ownership = reconstruct_case(fit_dir)
    tl_text = dumps_timeline(timeline)
    own_text = dumps_ownership(ownership)
    return {
        "timeline_sha256": hashlib.sha256(tl_text.encode("utf-8")).hexdigest(),
        "ownership_sha256": hashlib.sha256(own_text.encode("utf-8")).hexdigest(),
    }


def write_case_outputs(case_dir: Path, out_dir: Path) -> None:
    timeline, ownership = reconstruct_case(case_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "timeline.json").write_text(dumps_timeline(timeline), encoding="utf-8")
    (out_dir / "ownership.json").write_text(dumps_ownership(ownership), encoding="utf-8")