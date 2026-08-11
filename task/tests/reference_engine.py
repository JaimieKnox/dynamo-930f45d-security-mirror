#!/usr/bin/env python3
"""Independent verifier-side reconstruction engine (must stay under /tests)."""

from __future__ import annotations

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
    if not oplog and not txnlog:
        return []

    by_seq: dict[int, dict[str, Any]] = {}
    for row in oplog:
        by_seq[int(row["op_seq"])] = dict(row)

    txn_only: list[dict[str, Any]] = []
    for row in txnlog:
        seq = int(row["op_seq"])
        if seq not in by_seq:
            txn_only.append(dict(row))

    if not by_seq and txn_only:
        return sorted(
            txn_only,
            key=lambda r: (int(r["wall"]), int(r["op_seq"]), int(r["slot"]), int(r["gen"])),
        )

    seqs = sorted(by_seq.keys())
    wrap = False
    if len(seqs) >= 2:
        max_seq = max(seqs)
        min_seq = min(seqs)
        if max_seq - min_seq > OP_SEQ_MOD // 4:
            high = [s for s in seqs if s >= OP_SEQ_MOD // 2]
            low = [s for s in seqs if s < OP_SEQ_MOD // 2]
            if high and low:
                wrap = True

    if not wrap:
        ordered_seqs = seqs
    else:
        high = [s for s in seqs if s >= OP_SEQ_MOD // 2]
        low = [s for s in seqs if s < OP_SEQ_MOD // 2]
        high_walls = [int(by_seq[s]["wall"]) for s in high]
        low_walls = [int(by_seq[s]["wall"]) for s in low]
        txn_walls_high = [
            int(r["wall"]) for r in txn_only if int(r["op_seq"]) >= OP_SEQ_MOD // 2
        ]
        txn_walls_low = [
            int(r["wall"]) for r in txn_only if int(r["op_seq"]) < OP_SEQ_MOD // 2
        ]
        high_anchor = min(high_walls + txn_walls_high) if (high_walls or txn_walls_high) else 0
        low_anchor = min(low_walls + txn_walls_low) if (low_walls or txn_walls_low) else 0
        if high_anchor <= low_anchor:
            ordered_seqs = sorted(high) + sorted(low)
        else:
            ordered_seqs = sorted(low) + sorted(high)

    ordered: list[dict[str, Any]] = [by_seq[s] for s in ordered_seqs]

    if txn_only:
        if not ordered_seqs:
            return sorted(
                txn_only,
                key=lambda r: (int(r["wall"]), int(r["op_seq"]), int(r["slot"]), int(r["gen"])),
            )

        def seq_rank(seq: int) -> tuple[int, int]:
            if seq in ordered_seqs:
                return (ordered_seqs.index(seq), 0)
            best_i = 0
            best_dist = OP_SEQ_MOD
            for i, s in enumerate(ordered_seqs):
                if wrap:
                    start = ordered_seqs[0]
                    lin = (seq - start) % OP_SEQ_MOD
                    lin_s = (s - start) % OP_SEQ_MOD
                    if lin_s <= lin and (lin - lin_s) <= best_dist:
                        best_dist = lin - lin_s
                        best_i = i + 1
                else:
                    if s <= seq and (seq - s) <= best_dist:
                        best_dist = seq - s
                        best_i = i + 1
            return (best_i, seq)

        inserts = sorted(
            txn_only,
            key=lambda r: (
                seq_rank(int(r["op_seq"]))[0],
                int(r["wall"]),
                int(r["op_seq"]),
                int(r["slot"]),
                int(r["gen"]),
            ),
        )
        merged: list[dict[str, Any]] = []
        pending = list(inserts)
        for i, row in enumerate(ordered):
            while pending and seq_rank(int(pending[0]["op_seq"]))[0] <= i:
                merged.append(pending.pop(0))
            merged.append(row)
        while pending:
            merged.append(pending.pop(0))
        ordered = merged

    return ordered


def _coalesce(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    active_path_owner: dict[str, str] = {}
    poisoned: set[str] = set()

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
            if path in poisoned:
                return
            prev = active_path_owner.get(path)
            if prev is None:
                active_path_owner[path] = inc
                names[inc].add(path)
                return
            if prev == inc:
                names[inc].add(path)
                return
            poisoned.add(path)
            names[prev].discard(path)
            names[inc].discard(path)
            active_path_owner.pop(path, None)

        def release(path: str | None) -> None:
            if not path:
                return
            if path in poisoned:
                return
            names[inc].discard(path)
            if active_path_owner.get(path) == inc:
                active_path_owner.pop(path, None)

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

    for obj in objects:
        inc = _inc_id(int(obj["slot"]), int(obj["gen"]))
        ensure(inc)
        has_journal = any(
            e["slot"] == int(obj["slot"]) and e["gen"] == int(obj["gen"]) for e in timeline
        )
        if not has_journal:
            for n in obj.get("names") or []:
                if n not in poisoned:
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
                "streams": {k: streams[inc][k] for k in sorted(streams[inc].keys())},
            }
        )

    ownership = {
        "incarnations": incarnations,
        "poisoned_paths": sorted(poisoned),
    }
    return timeline, ownership


def dumps_timeline(timeline: list[dict[str, Any]]) -> str:
    return json.dumps(timeline, ensure_ascii=False, indent=2) + "\n"


def dumps_ownership(ownership: dict[str, Any]) -> str:
    return json.dumps(ownership, ensure_ascii=False, indent=2) + "\n"
