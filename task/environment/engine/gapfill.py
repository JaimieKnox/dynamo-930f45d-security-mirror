"""Txnlog gap fill for the shipped almost-correct engine.

Silent wrong: txn-origin RENAME_OLD rows are stashed into shared.pending_rename_olds
instead of being merged into the chronological stream. Coalesce is expected to pair
them, but the orchestration layer clears that buffer first on the long path.
"""

from __future__ import annotations

from typing import Any

from . import shared
from .rotate import OP_SEQ_MOD


def gapfill(
    rotated: list[dict[str, Any]],
    txnlog: list[dict[str, Any]],
    start: int | None,
) -> list[dict[str, Any]]:
    if start is None:
        txn_only = []
        for row in txnlog:
            tagged = dict(row)
            tagged["_src"] = "txnlog"
            if tagged.get("kind") == "RENAME_OLD":
                shared.pending_rename_olds.append(tagged)
            else:
                txn_only.append(tagged)
        return sorted(
            txn_only,
            key=lambda r: (int(r["wall"]), int(r["op_seq"]), int(r["slot"]), int(r["gen"])),
        )

    present = {int(r["op_seq"]) for r in rotated}
    txn_only: list[dict[str, Any]] = []
    for row in txnlog:
        seq = int(row["op_seq"])
        if seq in present:
            continue
        tagged = dict(row)
        tagged["_src"] = "txnlog"
        if tagged.get("kind") == "RENAME_OLD":
            shared.pending_rename_olds.append(tagged)
            continue
        txn_only.append(tagged)

    if not txn_only:
        return list(rotated)

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
    for row in rotated:
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
