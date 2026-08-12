"""Rename coalesce helper for the fit smoke pipeline."""

from __future__ import annotations

from typing import Any


def coalesce(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Coalesce adjacent same-incarnation rename pairs from the primary journal buffer."""
    out: list[dict[str, Any]] = []
    i = 0
    while i < len(ops):
        row = ops[i]
        nxt = ops[i + 1] if i + 1 < len(ops) else None
        if (
            nxt is not None
            and row.get("kind") == "RENAME_OLD"
            and nxt.get("kind") == "RENAME_NEW"
            and int(nxt["slot"]) == int(row["slot"])
            and int(nxt["gen"]) == int(row["gen"])
            and row.get("_src") == "oplog"
            and nxt.get("_src") == "oplog"
        ):
            out.append(
                {
                    "kind": "MOVE",
                    "slot": int(row["slot"]),
                    "gen": int(row["gen"]),
                    "op_seq": int(nxt["op_seq"]),
                    "wall": int(row["wall"]),
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
