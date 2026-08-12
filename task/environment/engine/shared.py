"""Process-local shared state across engine stages (fit-smoke scaffold)."""

from __future__ import annotations

from typing import Any

pending_rename_olds: list[dict[str, Any]] = []
poison_paths: set[str] = set()
streams_by_slot: dict[int, dict[str, str]] = {}
corpus_acc: dict[str, Any] = {
    "poisoned": set(),
    "incarnation_count": 0,
    "move_event_count": 0,
    "seen_cases": [],
}


def reset_case_buffers() -> None:
    """Reset per-case buffers (does not reset corpus_acc)."""
    pending_rename_olds.clear()
    poison_paths.clear()
    streams_by_slot.clear()


def reset_corpus_acc() -> None:
    corpus_acc["poisoned"] = set()
    corpus_acc["incarnation_count"] = 0
    corpus_acc["move_event_count"] = 0
    corpus_acc["seen_cases"] = []
