"""Verifier for vault timeline reconstruction outputs.

Residue contrasts are sealed in phase A.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

OUT_ROOT = Path("/app/output")
WORK = Path("/app/data/work")
SEAL_PATH = Path("/logs/verifier/sealed_expectations.json")
EVENT_KEYS = [
    "event_id",
    "slot",
    "gen",
    "kind",
    "time",
    "op_seq",
    "name",
    "name_from",
    "name_to",
    "stream",
    "content",
    "chain",
]
_CHAIN_RE = re.compile(r"^[0-9a-f]{16}$")


def _load_seal() -> dict:
    assert SEAL_PATH.is_file(), f"sealed expectations missing: {SEAL_PATH}"
    return json.loads(SEAL_PATH.read_text(encoding="utf-8"))


def _case_ids(seal: dict) -> tuple[str, ...]:
    ids = seal.get("case_ids")
    assert isinstance(ids, list) and ids, "seal missing case_ids"
    return tuple(ids)


def _work_case_ids() -> tuple[str, ...]:
    assert WORK.is_dir(), "missing /app/data/work"
    return tuple(sorted(p.name for p in WORK.iterdir() if p.is_dir()))


def _read_text(path: Path) -> str:
    assert path.is_file(), f"missing ordinary file: {path}"
    assert not path.is_symlink(), f"symlinked output rejected: {path}"
    resolved = path.resolve()
    assert str(resolved).startswith("/app/"), f"output escaped /app: {resolved}"
    return path.read_text(encoding="utf-8")


def _expected(seal: dict, case: str):
    blob = seal["cases"][case]
    return blob["timeline"], blob["ownership"]


def test_output_files_exist_for_every_work_case():
    """Success criterion 1: each work case has timeline.json and ownership.json under /app/output."""
    seal = _load_seal()
    work_ids = _work_case_ids()
    assert work_ids == _case_ids(seal)
    for case in work_ids:
        tl = OUT_ROOT / case / "timeline.json"
        own = OUT_ROOT / case / "ownership.json"
        assert tl.is_file() and not tl.is_symlink()
        assert own.is_file() and not own.is_symlink()


def test_timeline_schema_and_byte_contract():
    """Success criterion 2: timeline events match the contract schema, key order, and JSON text shape."""
    seal = _load_seal()
    for case in _case_ids(seal):
        raw = _read_text(OUT_ROOT / case / "timeline.json")
        data = json.loads(raw)
        assert isinstance(data, list)
        for ev in data:
            assert list(ev.keys()) == EVENT_KEYS
            assert type(ev["slot"]) is int
            assert type(ev["gen"]) is int
            assert type(ev["time"]) is int
            assert type(ev["op_seq"]) is int
            assert isinstance(ev["kind"], str)
            assert isinstance(ev["event_id"], str)
            assert isinstance(ev["chain"], str)
            assert _CHAIN_RE.fullmatch(ev["chain"]), ev["chain"]
        assert raw == seal["cases"][case]["timeline_text"]


def test_ownership_schema_and_byte_contract():
    """Success criterion 3: ownership matches schema, key order, sorting, and JSON text shape."""
    seal = _load_seal()
    for case in _case_ids(seal):
        raw = _read_text(OUT_ROOT / case / "ownership.json")
        data = json.loads(raw)
        assert list(data.keys()) == ["incarnations", "poisoned_paths"]
        assert isinstance(data["incarnations"], list)
        assert isinstance(data["poisoned_paths"], list)
        for inc in data["incarnations"]:
            assert list(inc.keys()) == ["id", "slot", "gen", "names", "streams"]
            assert type(inc["slot"]) is int
            assert type(inc["gen"]) is int
            assert isinstance(inc["names"], list)
            assert isinstance(inc["streams"], dict)
            assert list(inc["streams"].keys()) == sorted(inc["streams"].keys())
        assert data["poisoned_paths"] == sorted(data["poisoned_paths"])
        assert raw == seal["cases"][case]["ownership_text"]


def test_timeline_event_identity_and_order():
    """Success criterion 4: event identities, kinds, times, order, and chain match the contract."""
    seal = _load_seal()
    case_ids = _case_ids(seal)
    for case in case_ids:
        agent = json.loads(_read_text(OUT_ROOT / case / "timeline.json"))
        exp_tl, _ = _expected(seal, case)
        assert agent == exp_tl
        times = [(e["time"], e["event_id"]) for e in agent]
        assert times == sorted(times)
        for ev in agent:
            assert "chain" in ev and _CHAIN_RE.fullmatch(ev["chain"])
    if "echo" in case_ids:
        wrong_raw = seal["residue"]["echo_raw_op_seq_sort_timeline"]
        exp_echo_tl, _ = _expected(seal, "echo")
        assert wrong_raw != exp_echo_tl
        assert any(e["op_seq"] == 65533 for e in exp_echo_tl)
        assert any(e["kind"] == "MOVE" for e in exp_echo_tl)
        move = next(e for e in exp_echo_tl if e["kind"] == "MOVE" and e.get("name_from") == "echo/stage.txt")
        assert move["time"] == 1590
        assert move["op_seq"] == 0
        wrong_move_wall = seal["residue"]["echo_wrong_move_uses_new_wall_timeline"]
        assert wrong_move_wall != exp_echo_tl
        wrong_slot = seal["residue"]["echo_slot_only_merge_timeline"]
        assert wrong_slot != exp_echo_tl


def test_ownership_incarnations_streams_and_poison():
    """Success criterion 5: incarnation names, streams, and poisoned_paths match the contract."""
    seal = _load_seal()
    case_ids = _case_ids(seal)
    for case in case_ids:
        agent = json.loads(_read_text(OUT_ROOT / case / "ownership.json"))
        _, exp_own = _expected(seal, case)
        assert agent == exp_own
    if "echo" in case_ids:
        _, exp_echo = _expected(seal, "echo")
        assert exp_echo["poisoned_paths"] == ["echo/shared.dat"]
        wrong_stream = seal["residue"]["echo_stream_inherit_ownership"]
        assert wrong_stream != exp_echo
        wrong_poison = seal["residue"]["echo_no_poison_ownership"]
        assert wrong_poison != exp_echo
    if "foxtrot" in case_ids:
        _, exp_fox = _expected(seal, "foxtrot")
        ghost = next(i for i in exp_fox["incarnations"] if i["id"] == "62:1")
        assert ghost["names"] == ["fox/ghost.txt"]
        assert "aux" in ghost["streams"]
    if "golf" in case_ids:
        exp_golf_tl, exp_golf_own = _expected(seal, "golf")
        golf_move = next(
            e
            for e in exp_golf_tl
            if e["kind"] == "MOVE"
            and e["slot"] == 72
            and e["gen"] == 1
            and e.get("name_from") == "golf/carrier.txt"
            and e.get("name_to") == "golf/carrier_v2.txt"
        )
        assert golf_move["time"] == 1210
        assert golf_move["op_seq"] == 65528
        assert "chain" in golf_move and _CHAIN_RE.fullmatch(golf_move["chain"])
        assert "golf/shared.bin" in exp_golf_own["poisoned_paths"]
        ghost = next(i for i in exp_golf_own["incarnations"] if i["id"] == "76:1")
        assert "golf/shared.bin" not in ghost["names"]
        assert "golf/ghost.txt" in ghost["names"]
        wrong_half = seal["residue"]["golf_wrong_no_half_pair_coalesce_timeline"]
        assert wrong_half != exp_golf_tl
        wrong_si = seal["residue"]["golf_wrong_si_adopts_poisoned_ownership"]
        assert wrong_si != exp_golf_own
        wrong_move_wall = seal["residue"]["golf_wrong_move_uses_new_wall_timeline"]
        assert wrong_move_wall != exp_golf_tl
        wrong_move = next(
            e
            for e in wrong_move_wall
            if e["kind"] == "MOVE" and e.get("name_from") == "golf/carrier.txt"
        )
        assert wrong_move["time"] != golf_move["time"]
        assert any(
            exp_golf_tl[i]["chain"] != wrong_move_wall[i]["chain"]
            for i in range(min(len(exp_golf_tl), len(wrong_move_wall)))
        ), "NEW-wall MOVE rival must break chain integrity"
        wrong_genesis = seal["residue"]["golf_wrong_chain_genesis_timeline"]
        assert wrong_genesis != exp_golf_tl
        assert any(
            exp_golf_tl[i]["chain"] != wrong_genesis[i]["chain"]
            for i in range(min(len(exp_golf_tl), len(wrong_genesis)))
        ), "wrong chain genesis rival must diverge"

    if "hotel" in case_ids:
        exp_hotel_tl, exp_hotel_own = _expected(seal, "hotel")
        hotel_move = next(
            e
            for e in exp_hotel_tl
            if e["kind"] == "MOVE"
            and e["slot"] == 82
            and e["gen"] == 1
            and e.get("name_from") == "hotel/carrier.txt"
            and e.get("name_to") == "hotel/carrier_v2.txt"
        )
        assert hotel_move["time"] == 1510
        assert hotel_move["op_seq"] == 65528
        assert "hotel/shared.dat" in exp_hotel_own["poisoned_paths"]
        ghost = next(i for i in exp_hotel_own["incarnations"] if i["id"] == "89:1")
        assert "hotel/shared.dat" not in ghost["names"]
        assert "hotel/ghost.txt" in ghost["names"]
        root2 = next(i for i in exp_hotel_own["incarnations"] if i["id"] == "80:2")
        assert "meta" not in root2["streams"]
        assert len(exp_hotel_tl) >= 45

    if "juliet" in case_ids:
        exp_juliet_tl, exp_juliet_own = _expected(seal, "juliet")
        juliet_move = next(
            e
            for e in exp_juliet_tl
            if e["kind"] == "MOVE"
            and e["slot"] == 102
            and e["gen"] == 1
            and e.get("name_from") == "juliet/carrier.txt"
            and e.get("name_to") == "juliet/carrier_v2.txt"
        )
        assert juliet_move["time"] == 1410
        assert juliet_move["op_seq"] == 65525
        assert "juliet/shared.dat" in exp_juliet_own["poisoned_paths"]
        ghost = next(i for i in exp_juliet_own["incarnations"] if i["id"] == "109:1")
        assert "juliet/shared.dat" not in ghost["names"]
        assert "juliet/ghost.txt" in ghost["names"]
        root2 = next(i for i in exp_juliet_own["incarnations"] if i["id"] == "100:2")
        assert "meta" not in root2["streams"]
        assert any(e["kind"] == "RENAME_NEW" for e in exp_juliet_tl)
        assert len(exp_juliet_tl) >= 40
        wrong_move_wall = seal["residue"]["juliet_wrong_move_uses_new_wall_timeline"]
        assert wrong_move_wall != exp_juliet_tl
        wrong_move = next(
            e
            for e in wrong_move_wall
            if e["kind"] == "MOVE" and e.get("name_from") == "juliet/carrier.txt"
        )
        assert wrong_move["time"] != juliet_move["time"]
        wrong_genesis = seal["residue"]["juliet_wrong_chain_genesis_timeline"]
        assert wrong_genesis != exp_juliet_tl
        wrong_si = seal["residue"]["juliet_wrong_si_adopts_poisoned_ownership"]
        assert wrong_si != exp_juliet_own


def test_corpus_index_schema_and_byte_contract():
    """Success criterion 6: corpus_index.json matches schema and sealed aggregates."""
    seal = _load_seal()
    raw = _read_text(OUT_ROOT / "corpus_index.json")
    data = json.loads(raw)
    assert list(data.keys()) == [
        "case_ids",
        "poisoned_paths",
        "incarnation_count",
        "move_event_count",
        "name_claim_count",
        "chain_tips",
    ]
    assert data["case_ids"] == list(_case_ids(seal))
    assert "golf" in data["case_ids"]
    assert "hotel" in data["case_ids"]
    assert "juliet" in data["case_ids"]
    assert data["poisoned_paths"] == sorted(data["poisoned_paths"])
    assert type(data["incarnation_count"]) is int
    assert type(data["move_event_count"]) is int
    assert type(data["name_claim_count"]) is int
    assert isinstance(data["chain_tips"], dict)
    assert list(data["chain_tips"].keys()) == sorted(data["chain_tips"].keys())
    assert set(data["chain_tips"]) == set(data["case_ids"])
    for cid, tip in data["chain_tips"].items():
        exp_tl, _ = _expected(seal, cid)
        assert tip == exp_tl[-1]["chain"]
    assert "hotel" in data["chain_tips"]
    assert "juliet" in data["chain_tips"]
    assert raw == seal["corpus_index_text"]
    assert data == seal["corpus_index"]
