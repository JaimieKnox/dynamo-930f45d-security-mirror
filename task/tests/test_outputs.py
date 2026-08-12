"""Verifier for vault timeline reconstruction outputs.

Residue contrasts are sealed in phase A.
"""

from __future__ import annotations

import json
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
]


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
    """Success criterion 4: event identities, kinds, times, and sort order match the contract."""
    seal = _load_seal()
    case_ids = _case_ids(seal)
    for case in case_ids:
        agent = json.loads(_read_text(OUT_ROOT / case / "timeline.json"))
        exp_tl, _ = _expected(seal, case)
        assert agent == exp_tl
        times = [(e["time"], e["op_seq"], e["event_id"]) for e in agent]
        assert times == sorted(times)
    if "echo" in case_ids:
        wrong_raw = seal["residue"]["echo_raw_op_seq_sort_timeline"]
        exp_echo_tl, _ = _expected(seal, "echo")
        assert wrong_raw != exp_echo_tl
        assert any(e["op_seq"] == 65533 for e in exp_echo_tl)
        assert any(e["kind"] == "MOVE" for e in exp_echo_tl)
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
        assert any(
            e["kind"] == "MOVE"
            and e["slot"] == 72
            and e["gen"] == 1
            and e.get("name_from") == "golf/carrier.txt"
            and e.get("name_to") == "golf/carrier_v2.txt"
            for e in exp_golf_tl
        )
        assert "golf/shared.bin" in exp_golf_own["poisoned_paths"]
        ghost = next(i for i in exp_golf_own["incarnations"] if i["id"] == "76:1")
        assert "golf/shared.bin" not in ghost["names"]
        assert "golf/ghost.txt" in ghost["names"]
        wrong_half = seal["residue"]["golf_wrong_no_half_pair_coalesce_timeline"]
        assert wrong_half != exp_golf_tl
        wrong_si = seal["residue"]["golf_wrong_si_adopts_poisoned_ownership"]
        assert wrong_si != exp_golf_own


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
    ]
    assert data["case_ids"] == list(_case_ids(seal))
    assert "golf" in data["case_ids"]
    assert data["poisoned_paths"] == sorted(data["poisoned_paths"])
    assert type(data["incarnation_count"]) is int
    assert type(data["move_event_count"]) is int
    assert raw == seal["corpus_index_text"]
    assert data == seal["corpus_index"]

