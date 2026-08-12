"""Oldest-first circular oplog rotation (mostly correct)."""

from __future__ import annotations

from typing import Any

OP_SEQ_MOD = 65536


def rotate_oplog(oplog: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int | None]:
    """Return (rotated oplog rows tagged _src=oplog, start_seq)."""
    if not oplog:
        return [], None
    by_seq: dict[int, dict[str, Any]] = {}
    for row in oplog:
        tagged = dict(row)
        tagged["_src"] = "oplog"
        by_seq[int(row["op_seq"])] = tagged
    oldest = min(
        by_seq.values(),
        key=lambda r: (int(r["wall"]), int(r["op_seq"]), int(r["slot"]), int(r["gen"])),
    )
    start = int(oldest["op_seq"])
    ordered_seqs = sorted(by_seq.keys(), key=lambda s: (s - start) % OP_SEQ_MOD)
    return [by_seq[s] for s in ordered_seqs], start
