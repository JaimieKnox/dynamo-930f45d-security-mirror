"""Process-local scratch buffers for staged reconstruction passes."""

from __future__ import annotations

from typing import Any

pending_rename_olds: list[dict[str, Any]] = []
stream_scratch: dict[tuple[int, int], dict[str, str]] = {}
path_claims: dict[str, str] = {}


def reset_case_buffers() -> None:
    """Clear per-case scratch before a new case reconstruction."""
    pending_rename_olds.clear()
    stream_scratch.clear()
    path_claims.clear()
