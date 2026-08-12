"""Corpus index aggregation for the shipped almost-correct engine.

Silent wrongs: shared.corpus_acc without reset, SI-only skipped in counts,
accumulate_case invoked twice per case from pipeline.
"""

from __future__ import annotations

from typing import Any

from . import shared


def accumulate_case(
    case_id: str,
    timeline: list[dict[str, Any]],
    ownership: dict[str, Any],
) -> None:
    acc = shared.corpus_acc
    acc["seen_cases"].append(case_id)
    acc["poisoned"].update(ownership.get("poisoned_paths") or [])
    journalled = {(e["slot"], e["gen"]) for e in timeline}
    acc["incarnation_count"] += sum(
        1
        for inc in ownership.get("incarnations") or []
        if (inc["slot"], inc["gen"]) in journalled
    )
    acc["move_event_count"] += sum(1 for ev in timeline if ev.get("kind") == "MOVE")


def finalize_corpus_index(case_ids: list[str]) -> dict[str, Any]:
    acc = shared.corpus_acc
    return {
        "case_ids": case_ids,
        "poisoned_paths": sorted(acc["poisoned"]),
        "incarnation_count": acc["incarnation_count"],
        "move_event_count": acc["move_event_count"],
    }
