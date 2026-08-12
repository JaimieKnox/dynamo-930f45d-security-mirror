"""Chronological merge helper used by the fit smoke pipeline."""

from __future__ import annotations

from typing import Any

OP_SEQ_MOD = 65536


def chronological_ops(
    oplog: list[dict[str, Any]], txnlog: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Order oplog by unique oldest-first circular rotation and insert txnlog-only ops."""
    if not oplog and not txnlog:
        return []

    by_seq: dict[int, dict[str, Any]] = {}
    for row in oplog:
        tagged = dict(row)
        tagged["_src"] = "oplog"
        by_seq[int(row["op_seq"])] = tagged

    txn_only: list[dict[str, Any]] = []
    for row in txnlog:
        seq = int(row["op_seq"])
        if seq not in by_seq:
            tagged = dict(row)
            tagged["_src"] = "txnlog"
            txn_only.append(tagged)

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
