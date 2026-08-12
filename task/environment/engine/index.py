"""Corpus index helpers used by the fit smoke pipeline."""

from __future__ import annotations

from typing import Any


def aggregate_case_stats(
    timeline: list[dict[str, Any]], ownership: dict[str, Any]
) -> tuple[set[str], int, int]:
    """Return (poisoned, incarnation_count_delta, move_event_count_delta)."""
    poisoned = set(ownership.get("poisoned_paths") or [])
    journalled = {(e["slot"], e["gen"]) for e in timeline}
    incarnation_count = sum(
        1
        for inc in ownership.get("incarnations") or []
        if (inc["slot"], inc["gen"]) in journalled
    )
    move_event_count = sum(1 for ev in timeline if ev.get("kind") == "MOVE")
    return poisoned, incarnation_count, move_event_count


def build_corpus_index_from_cases(
    case_ids: list[str],
    case_results: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]],
) -> dict[str, Any]:
    poisoned: set[str] = set()
    incarnation_count = 0
    move_event_count = 0
    for cid in case_ids:
        timeline, ownership = case_results[cid]
        p, ic, mc = aggregate_case_stats(timeline, ownership)
        poisoned.update(p)
        incarnation_count += ic
        move_event_count += mc
    return {
        "case_ids": case_ids,
        "poisoned_paths": sorted(poisoned),
        "incarnation_count": incarnation_count,
        "move_event_count": move_event_count,
    }
