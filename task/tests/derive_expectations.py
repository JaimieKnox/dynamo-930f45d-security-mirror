#!/usr/bin/env python3
"""Phase A: seal graded expectations, then remove the reference engine."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from reference_engine import (
    annotate_chains,
    build_corpus_index,
    dumps_corpus_index,
    dumps_ownership,
    dumps_timeline,
    reconstruct_case,
)

TESTS = Path(__file__).resolve().parent
TESTS_IN = TESTS / "inputs"
SEAL_PATH = Path("/logs/verifier/sealed_expectations.json")


def discover_cases() -> tuple[str, ...]:
    if not TESTS_IN.is_dir():
        raise SystemExit(f"missing inputs: {TESTS_IN}")
    names = tuple(sorted(p.name for p in TESTS_IN.iterdir() if p.is_dir()))
    if not names:
        raise SystemExit("no case dirs under /tests/inputs")
    return names


def wrong_slot_only_merge(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Merge all gens of a slot into gen=min (identity without generation)."""
    timeline, ownership = reconstruct_case(case_dir)
    tl = copy.deepcopy(timeline)
    for ev in tl:
        ev["gen"] = 1
        ev["event_id"] = f"{ev['slot']}:1:{ev['op_seq']}:{ev['kind']}"
        ev.pop("chain", None)
    tl.sort(key=lambda e: (e["time"], e["event_id"]))
    annotate_chains(tl)
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
    annotate_chains(tl)
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


def wrong_no_half_pair_coalesce(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Refuse to coalesce MOVE when rename halves would require cross-ledger adjacency."""
    timeline, ownership = reconstruct_case(case_dir)
    tl = copy.deepcopy(timeline)
    expanded: list[dict[str, Any]] = []
    for ev in tl:
        if ev.get("kind") == "MOVE":
            slot = ev["slot"]
            gen = ev["gen"]
            expanded.append(
                {
                    "event_id": f"{slot}:{gen}:{ev['op_seq']}:RENAME_NEW",
                    "slot": slot,
                    "gen": gen,
                    "kind": "RENAME_NEW",
                    "time": ev["time"],
                    "op_seq": ev["op_seq"],
                    "name": ev.get("name_to"),
                    "name_from": None,
                    "name_to": None,
                    "stream": None,
                    "content": None,
                }
            )
        else:
            ev = dict(ev)
            ev.pop("chain", None)
            expanded.append(ev)
    expanded.sort(key=lambda e: (e["time"], e["event_id"]))
    annotate_chains(expanded)
    return expanded, ownership


def wrong_move_uses_new_wall(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rival: coalesced MOVE time taken from RENAME_NEW wall instead of legacy OLD wall.

    Re-sorting and recomputing chain hashes cascades failures after the first wrong MOVE.
    """
    import json as _json

    def load(p: Path):
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(_json.loads(line))
        return rows

    timeline, ownership = reconstruct_case(case_dir)
    oplog = load(case_dir / "oplog.jsonl")
    txnlog = load(case_dir / "txnlog.jsonl")
    new_walls: dict[tuple[int, int, int], int] = {}
    for row in list(oplog) + list(txnlog):
        if row.get("kind") == "RENAME_NEW":
            key = (int(row["slot"]), int(row["gen"]), int(row["op_seq"]))
            new_walls[key] = int(row["wall"])
    tl = copy.deepcopy(timeline)
    for ev in tl:
        if ev.get("kind") != "MOVE":
            continue
        key = (int(ev["slot"]), int(ev["gen"]), int(ev["op_seq"]))
        if key in new_walls:
            ev["time"] = new_walls[key]
        ev.pop("chain", None)
    for ev in tl:
        ev.pop("chain", None)
    tl.sort(key=lambda e: (e["time"], e["event_id"]))
    annotate_chains(tl)
    return tl, ownership


def wrong_si_adopts_poisoned(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """SI-only residual adopts object-table names even when already poisoned."""
    timeline, ownership = reconstruct_case(case_dir)
    own = copy.deepcopy(ownership)
    objects = []
    obj_path = case_dir / "objects.jsonl"
    if obj_path.is_file():
        for line in obj_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                objects.append(json.loads(line))
    journalled = {(e["slot"], e["gen"]) for e in timeline}
    poisoned = set(own.get("poisoned_paths") or [])
    by_id = {i["id"]: i for i in own["incarnations"]}
    for obj in objects:
        key = (int(obj["slot"]), int(obj["gen"]))
        if key in journalled:
            continue
        inc_id = f"{key[0]}:{key[1]}"
        if inc_id not in by_id:
            by_id[inc_id] = {
                "id": inc_id,
                "slot": key[0],
                "gen": key[1],
                "names": [],
                "streams": {},
            }
        names = set(by_id[inc_id]["names"])
        for n in obj.get("names") or []:
            if n in poisoned:
                names.add(n)
        by_id[inc_id]["names"] = sorted(names)
        streams = dict(by_id[inc_id]["streams"])
        for sname, digest in (obj.get("streams") or {}).items():
            streams[sname] = digest
        by_id[inc_id]["streams"] = {k: streams[k] for k in sorted(streams)}
    own["incarnations"] = [
        by_id[i]
        for i in sorted(by_id.keys(), key=lambda x: (int(x.split(":")[0]), int(x.split(":")[1])))
    ]
    return timeline, own


def wrong_chain_genesis(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Rival: chain genesis token differs from the exporter profile."""
    import hashlib

    timeline, ownership = reconstruct_case(case_dir)
    tl = copy.deepcopy(timeline)
    prev: str | None = None
    for ev in tl:
        eid = str(ev["event_id"])
        t = int(ev["time"])
        if prev is None:
            raw = f"VAULT0|{eid}|{t}"
        else:
            raw = f"{prev}|{eid}|{t}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        ev["chain"] = digest
        prev = digest
    return tl, ownership


def main() -> int:
    SEAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    cases_list = discover_cases()
    cases = {}
    for name in cases_list:
        tl, own = reconstruct_case(TESTS_IN / name)
        cases[name] = {
            "timeline": tl,
            "ownership": own,
            "timeline_text": dumps_timeline(tl),
            "ownership_text": dumps_ownership(own),
        }

    residue = {}
    if "echo" in cases_list:
        wrong_echo_raw, _ = wrong_raw_op_seq_sort(TESTS_IN / "echo")
        wrong_echo_slot, _ = wrong_slot_only_merge(TESTS_IN / "echo")
        _, wrong_echo_stream = wrong_stream_inherit(TESTS_IN / "echo")
        _, wrong_echo_poison = wrong_no_poison(TESTS_IN / "echo")
        residue.update(
            {
                "echo_raw_op_seq_sort_timeline": wrong_echo_raw,
                "echo_slot_only_merge_timeline": wrong_echo_slot,
                "echo_stream_inherit_ownership": wrong_echo_stream,
                "echo_no_poison_ownership": wrong_echo_poison,
            }
        )
    if "golf" in cases_list:
        wrong_golf_half, _ = wrong_no_half_pair_coalesce(TESTS_IN / "golf")
        _, wrong_golf_si = wrong_si_adopts_poisoned(TESTS_IN / "golf")
        wrong_golf_move_wall, _ = wrong_move_uses_new_wall(TESTS_IN / "golf")
        wrong_golf_genesis, _ = wrong_chain_genesis(TESTS_IN / "golf")
        residue.update(
            {
                "golf_wrong_no_half_pair_coalesce_timeline": wrong_golf_half,
                "golf_wrong_si_adopts_poisoned_ownership": wrong_golf_si,
                "golf_wrong_move_uses_new_wall_timeline": wrong_golf_move_wall,
                "golf_wrong_chain_genesis_timeline": wrong_golf_genesis,
            }
        )
    if "echo" in cases_list and "echo_wrong_move_uses_new_wall_timeline" not in residue:
        wrong_echo_move_wall, _ = wrong_move_uses_new_wall(TESTS_IN / "echo")
        residue["echo_wrong_move_uses_new_wall_timeline"] = wrong_echo_move_wall
    if "juliet" in cases_list:
        wrong_juliet_move_wall, _ = wrong_move_uses_new_wall(TESTS_IN / "juliet")
        wrong_juliet_genesis, _ = wrong_chain_genesis(TESTS_IN / "juliet")
        _, wrong_juliet_si = wrong_si_adopts_poisoned(TESTS_IN / "juliet")
        residue.update(
            {
                "juliet_wrong_move_uses_new_wall_timeline": wrong_juliet_move_wall,
                "juliet_wrong_chain_genesis_timeline": wrong_juliet_genesis,
                "juliet_wrong_si_adopts_poisoned_ownership": wrong_juliet_si,
            }
        )

    corpus_index = build_corpus_index(TESTS_IN)
    payload = {
        "case_ids": list(cases_list),
        "cases": cases,
        "residue": residue,
        "corpus_index": corpus_index,
        "corpus_index_text": dumps_corpus_index(corpus_index),
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
