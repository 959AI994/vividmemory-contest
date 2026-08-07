"""Append-only JSONL checkpoint + resume helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator


def append_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> int:
    """Append records as JSONL. Returns number of records written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with p.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False))
            f.write("\n")
            written += 1
    return written


def read_jsonl(path: str | Path) -> Iterator[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def load_completed_keys(path: str | Path, key_field: str) -> set[str]:
    """Load a set of completed identifiers to skip on resume."""
    return {r[key_field] for r in read_jsonl(path) if key_field in r}
