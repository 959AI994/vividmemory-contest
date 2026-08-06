"""Runner configuration model + YAML loader."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - developer-time guard
    raise RuntimeError(
        "PyYAML is required for the runner. Install: pip install pyyaml"
    ) from exc


@dataclass
class DatasetConfig:
    name: str
    path: str
    max_conversations: int | None = None
    max_questions_per_conversation: int | None = None


@dataclass
class RunConfig:
    adapter_base_url: str = "http://localhost:8000"
    top_k: int = 10
    add_concurrency: int = 8
    search_concurrency: int = 16
    request_timeout_seconds: float = 300.0
    datasets: list[DatasetConfig] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RunConfig":
        with open(path, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = yaml.safe_load(f) or {}
        datasets = [DatasetConfig(**d) for d in raw.pop("datasets", []) or []]
        return cls(datasets=datasets, **raw)
