"""Orchestration for the shipped vault engine fit smoke scaffold."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import shared
from .chrono import chronological_ops
from .coalesce import coalesce
from .index import build_corpus_index_from_cases
from .ownership import build_ownership


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


def _event_id(slot: int, gen: int, op_seq: int, kind: str) -> str:
    return f"{slot}:{gen}:{op_seq}:{kind}"


def dumps_timeline(timeline: list[dict[str, Any]]) -> str:
    return json.dumps(timeline, ensure_ascii=False, indent=2) + "\n"


def dumps_ownership(ownership: dict[str, Any]) -> str:
    return json.dumps(ownership, ensure_ascii=False, indent=2) + "\n"


def dumps_corpus_index(index: dict[str, Any]) -> str:
    return json.dumps(index, ensure_ascii=False, indent=2) + "\n"


def reconstruct_case(case_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    objects = _load_jsonl(case_dir / "objects.jsonl")
    oplog = _load_jsonl(case_dir / "oplog.jsonl")
    txnlog = _load_jsonl(case_dir / "txnlog.jsonl")

    shared.reset_case_buffers()
    ordered = chronological_ops(oplog, txnlog)
    shared.pending_rename_olds.clear()
    events_raw = coalesce(ordered)

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
    ownership = build_ownership(timeline, objects)
    return timeline, ownership


def write_case_outputs(case_dir: Path, out_dir: Path) -> None:
    timeline, ownership = reconstruct_case(case_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "timeline.json").write_text(dumps_timeline(timeline), encoding="utf-8")
    (out_dir / "ownership.json").write_text(dumps_ownership(ownership), encoding="utf-8")


def build_corpus_index(work_root: Path) -> dict[str, Any]:
    case_ids = sorted(p.name for p in work_root.iterdir() if p.is_dir())
    case_results = {cid: reconstruct_case(work_root / cid) for cid in case_ids}
    return build_corpus_index_from_cases(case_ids, case_results)


def fit_smoke(fit_dir: Path) -> dict[str, str]:
    """Return sha256 digests of pipeline JSON text for a fit pack."""
    timeline, ownership = reconstruct_case(fit_dir)
    tl_text = dumps_timeline(timeline)
    own_text = dumps_ownership(ownership)
    return {
        "timeline_sha256": hashlib.sha256(tl_text.encode("utf-8")).hexdigest(),
        "ownership_sha256": hashlib.sha256(own_text.encode("utf-8")).hexdigest(),
    }
