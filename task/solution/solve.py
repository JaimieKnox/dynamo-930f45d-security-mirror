#!/usr/bin/env python3
"""Oracle entry: reconstruct every work case under /app/data/work."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/solution")
from recon import write_case_outputs, write_corpus_index  # noqa: E402

WORK = Path("/app/data/work")
OUT = Path("/app/output")


def main() -> None:
    if not WORK.is_dir():
        raise SystemExit("missing /app/data/work")
    for case_dir in sorted(p for p in WORK.iterdir() if p.is_dir()):
        write_case_outputs(case_dir, OUT / case_dir.name)
    write_corpus_index(WORK, OUT / "corpus_index.json")


if __name__ == "__main__":
    main()
