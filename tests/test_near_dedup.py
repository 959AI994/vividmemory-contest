"""Phase 4C — token-Jaccard near-duplicate suppression in _normalize_results."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contest-adapter"))

from app.main import _jaccard, _normalize_results, _tokenize_for_dedup  # noqa: E402


def _row(row_id: str, text: str, score: float | None = None) -> dict:
    row: dict = {"id": row_id, "text": text}
    if score is not None:
        row["scores"] = {"final": score}
    return row


def test_dedup_disabled_preserves_current_behavior():
    """threshold=0.0 must keep every non-exact-dup input, matching prior behavior."""
    raw = [
        _row("1", "Alice moved to Seattle in 2024.", score=0.9),
        _row("2", "Alice has moved to Seattle in 2024.", score=0.8),
        _row("3", "Bob lives in Boston.", score=0.7),
    ]
    items = _normalize_results(raw, top_k=10, near_dedup_threshold=0.0)
    assert [i.id for i in items] == ["1", "2", "3"]


def test_dedup_collapses_high_jaccard_pair():
    """Two nearly-identical summaries should collapse; the higher-scored survives."""
    raw = [
        _row("1", "Alice moved to Seattle in 2024.", score=0.9),
        _row("2", "Alice has moved to Seattle in 2024.", score=0.8),  # near-dup of 1
        _row("3", "Bob lives in Boston.", score=0.7),
    ]
    items = _normalize_results(raw, top_k=10, near_dedup_threshold=0.8)
    ids = [i.id for i in items]
    assert "1" in ids  # higher-scored survives
    assert "2" not in ids  # near-dup dropped
    assert "3" in ids  # unrelated content kept


def test_dedup_does_not_collapse_unrelated():
    raw = [
        _row("1", "Alice moved to Seattle in 2024.", score=0.9),
        _row("2", "Bob's favorite color is red.", score=0.85),
        _row("3", "Charlie plays the violin.", score=0.8),
    ]
    items = _normalize_results(raw, top_k=10, near_dedup_threshold=0.8)
    assert [i.id for i in items] == ["1", "2", "3"]


def test_dedup_respects_top_k():
    raw = [
        _row("1", "A", score=0.9),
        _row("2", "B", score=0.8),
        _row("3", "C", score=0.7),
        _row("4", "D", score=0.6),
    ]
    items = _normalize_results(raw, top_k=2, near_dedup_threshold=0.5)
    assert len(items) == 2


def test_dedup_higher_scored_seen_first_wins():
    """First-in-order retention: with pre-sorted input, lower-scored dup is dropped."""
    raw = [
        _row("1", "The capital of France is Paris.", score=0.95),
        _row("2", "Paris is the capital of France.", score=0.5),  # near-dup
    ]
    items = _normalize_results(raw, top_k=5, near_dedup_threshold=0.7)
    assert len(items) == 1
    assert items[0].id == "1"


def test_jaccard_edge_cases():
    assert _jaccard(frozenset(), frozenset()) == 0.0
    assert _jaccard(frozenset({"a"}), frozenset()) == 0.0
    assert _jaccard(frozenset({"a"}), frozenset({"a"})) == 1.0
    assert _jaccard(frozenset({"a", "b"}), frozenset({"b", "c"})) == 1 / 3


def test_tokenize_lowercases_and_strips_punct():
    tokens = _tokenize_for_dedup("Alice, MOVED to Seattle-2024!")
    assert "alice" in tokens
    assert "moved" in tokens
    assert "seattle" in tokens
    assert "2024" in tokens
    # punctuation and casing gone
    assert "Alice" not in tokens
    assert "," not in tokens
