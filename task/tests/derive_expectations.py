#!/usr/bin/env python3
"""Phase A: seal graded expectations, then remove the reference engine."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from reference_engine import dumps_ownership, dumps_timeline, reconstruct_case

TESTS = Path(__file__).resolve().parent
TESTS_IN = TESTS / "inputs"
SEAL_PATH = Path("/logs/verifier/sealed_expectations.json")
CASES = ("echo", "foxtrot")


def wrong_slot_only_merge(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge all gens of a slot into gen=min (identity without generation)."""
    timeline, ownership = reconstruct_case(case_dir)
    tl = copy.deepcopy(timeline)
    for ev in tl:
        ev["gen"] = 1
        ev["event_id"] = f"{ev['slot']}:1:{ev['op_seq']}:{ev['kind']}"
    own = copy.deepcopy(ownership)
    # Collapse incarnations by slot
    by_slot: dict[int, dict[str, Any]] = {}
    for inc in own["incarnations"]:
        slot = int(inc["slot"])
        if slot not in by_slot:
            by_slot[slot] = {
                "id": f"{slot}:1",
                "slot": slot,
                "gen": 1,
                "names": set(inc["names"]),
                "streams": dict(inc["streams"]),
            }
        else:
            by_slot[slot]["names"].update(inc["names"])
            by_slot[slot]["streams"].update(inc["streams"])
    own["incarnations"] = [
        {
            "id": v["id"],
            "slot": v["slot"],
            "gen": 1,
            "names": sorted(v["names"]),
            "streams": {k: v["streams"][k] for k in sorted(v["streams"])},
        }
        for v in sorted(by_slot.values(), key=lambda x: x["slot"])
    ]
    return tl, own


def wrong_raw_op_seq_sort(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Sort oplog by raw op_seq integers (breaks wrap)."""
    import json

    def load(p: Path):
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    oplog = sorted(load(case_dir / "oplog.jsonl"), key=lambda r: int(r["op_seq"]))
    # Ignore txnlog entirely and skip coalesce for a strong residue flip on delta.
    tl = []
    for row in oplog:
        kind = row["kind"]
        tl.append(
            {
                "event_id": f"{row['slot']}:{row['gen']}:{row['op_seq']}:{kind}",
                "slot": int(row["slot"]),
                "gen": int(row["gen"]),
                "kind": kind,
                "time": int(row["wall"]),
                "op_seq": int(row["op_seq"]),
                "name": row.get("name"),
                "name_from": None,
                "name_to": None,
                "stream": row.get("stream"),
                "content": row.get("content"),
            }
        )
    tl.sort(key=lambda e: (e["op_seq"], e["event_id"]))
    _, own = reconstruct_case(case_dir)
    return tl, own


def wrong_stream_inherit(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Carry streams from prior gen in the same slot into later gens."""
    timeline, ownership = reconstruct_case(case_dir)
    own = copy.deepcopy(ownership)
    by_id = {i["id"]: i for i in own["incarnations"]}
    # For each slot, merge streams from lower gens into higher gens.
    slots: dict[int, list[dict[str, Any]]] = {}
    for inc in own["incarnations"]:
        slots.setdefault(int(inc["slot"]), []).append(inc)
    for slot, incs in slots.items():
        incs_sorted = sorted(incs, key=lambda x: int(x["gen"]))
        carried: dict[str, str] = {}
        for inc in incs_sorted:
            carried.update(inc["streams"])
            inc["streams"] = {k: carried[k] for k in sorted(carried.keys())}
            by_id[inc["id"]] = inc
    own["incarnations"] = [by_id[i["id"]] for i in ownership["incarnations"]]
    return timeline, own


def wrong_no_poison(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep last writer on conflicting paths (pairwise pop / revive)."""
    timeline, ownership = reconstruct_case(case_dir)
    own = copy.deepcopy(ownership)
    # Clear poison and assign collide path to last incarnation that wrote it.
    path = None
    if ownership.get("poisoned_paths"):
        path = ownership["poisoned_paths"][0]
    if path:
        own["poisoned_paths"] = []
        last = None
        for ev in timeline:
            if ev.get("name") == path or ev.get("name_to") == path:
                last = f"{ev['slot']}:{ev['gen']}"
        for inc in own["incarnations"]:
            if path in inc["names"]:
                inc["names"] = [n for n in inc["names"] if n != path]
            if last and inc["id"] == last:
                inc["names"] = sorted(set(inc["names"]) | {path})
    return timeline, own


def main() -> int:
    SEAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    cases = {}
    for name in CASES:
        tl, own = reconstruct_case(TESTS_IN / name)
        cases[name] = {
            "timeline": tl,
            "ownership": own,
            "timeline_text": dumps_timeline(tl),
            "ownership_text": dumps_ownership(own),
        }

    wrong_echo_raw, _ = wrong_raw_op_seq_sort(TESTS_IN / "echo")
    wrong_echo_slot, _ = wrong_slot_only_merge(TESTS_IN / "echo")
    _, wrong_echo_stream = wrong_stream_inherit(TESTS_IN / "echo")
    _, wrong_echo_poison = wrong_no_poison(TESTS_IN / "echo")

    payload = {
        "cases": cases,
        "residue": {
            "echo_raw_op_seq_sort_timeline": wrong_echo_raw,
            "echo_slot_only_merge_timeline": wrong_echo_slot,
            "echo_stream_inherit_ownership": wrong_echo_stream,
            "echo_no_poison_ownership": wrong_echo_poison,
        },
    }
    SEAL_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for path in (
        TESTS / "reference_engine.py",
        Path(__file__).resolve(),
    ):
        if path.is_file():
            os.remove(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
