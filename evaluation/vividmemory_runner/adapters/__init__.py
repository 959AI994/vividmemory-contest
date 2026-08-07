"""Dataset adapter shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnRecord:
    """A single conversation turn ready for /add messages payload."""

    role: str
    content: str
    timestamp_ms: int | None = None


@dataclass
class ConversationRecord:
    """A logical conversation to ingest as one or more /add batches."""

    conversation_id: str
    speaker_key: str
    turns: list[TurnRecord]
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryRecord:
    """A single benchmark query with gold-answer + evidence for proxy metrics."""

    query_id: str
    conversation_id: str
    speaker_key: str
    query: str
    gold_answer: str | None = None
    evidence_texts: list[str] = field(default_factory=list)
    options: list[str] | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
