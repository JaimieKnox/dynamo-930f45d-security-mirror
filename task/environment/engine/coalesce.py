"""Rename coalesce for the shipped almost-correct engine.

Consumes adjacent RENAME_OLD+RENAME_NEW in the merged stream, and would also
consume shared.pending_rename_olds when present. Pipeline clears that buffer
before this stage runs, so cross-ledger halves never meet.
"""

from __future__ import annotations

from typing import Any

from . import shared


def coalesce(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    work = list(ops)
    if shared.pending_rename_olds:
        spliced: list[dict[str, Any]] = []
        pend = list(shared.pending_rename_olds)
        for row in work:
            if (
                pend
                and row.get("kind") == "RENAME_NEW"
                and int(pend[0]["slot"]) == int(row["slot"])
                and int(pend[0]["gen"]) == int(row["gen"])
            ):
                spliced.append(pend.pop(0))
            spliced.append(row)
        work = spliced
        shared.pending_rename_olds[:] = pend

    out: list[dict[str, Any]] = []
    i = 0
    while i < len(work):
        row = work[i]
        nxt = work[i + 1] if i + 1 < len(work) else None
        if (
            nxt is not None
            and row.get("kind") == "RENAME_OLD"
            and nxt.get("kind") == "RENAME_NEW"
            and int(nxt["slot"]) == int(row["slot"])
            and int(nxt["gen"]) == int(row["gen"])
        ):
            out.append(
                {
                    "kind": "MOVE",
                    "slot": int(row["slot"]),
                    "gen": int(row["gen"]),
                    "op_seq": int(nxt["op_seq"]),
                    "wall": int(nxt["wall"]),
                    "name_from": row.get("name"),
                    "name_to": nxt.get("name"),
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
