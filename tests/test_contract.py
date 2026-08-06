"""Contract tests for contest adapter schemas and helpers (no live server)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contest-adapter"))

from app.client import build_recall_query, format_conversation_document, user_to_bank_id  # noqa: E402
from app.main import _normalize_results  # noqa: E402
from app.schemas import AddRequest, SearchRequest, SearchResponse  # noqa: E402


def test_add_schema_accepts_official_payload():
    body = AddRequest.model_validate(
        {
            "request_id": "eval:run_xxx:chunk-0",
            "messages": [
                {"role": "user", "timestamp": 1704067200000, "content": "memory text"},
            ],
            "user_id": "eval:run_xxx:user-0",
            "session_id": "eval:run_xxx:session-0",
        }
    )
    assert body.request_id.endswith("chunk-0")
    assert body.messages[0].content == "memory text"


def test_search_schema_top_k_bounds():
    ok = SearchRequest(query="q", user_id="u", top_k=1)
    assert ok.top_k == 1
    with pytest.raises(ValidationError):
        SearchRequest(query="q", user_id="u", top_k=0)
    with pytest.raises(ValidationError):
        SearchRequest(query="q", user_id="u", top_k=101)


def test_search_response_empty_shape():
    resp = SearchResponse(data=[])
    assert resp.model_dump() == {"data": []}


def test_user_to_bank_deterministic_and_isolated():
    a = user_to_bank_id("user-a")
    b = user_to_bank_id("user-b")
    assert a.startswith("contest-")
    assert a == user_to_bank_id("user-a")
    assert a != b


def test_conversation_document_preserves_order_and_ids():
    from app.schemas import Message

    doc = format_conversation_document(
        messages=[
            Message(role="user", content="I live in Boston.", timestamp=1704067200000),
            Message(role="assistant", content="Understood.", timestamp=1704067203000),
        ],
        request_id="req-1",
        session_id="sess-1",
    )
    assert "request_id: req-1" in doc
    assert "session_id: sess-1" in doc
    assert doc.index("Boston") < doc.index("Understood")


def test_build_recall_query_options_optional():
    assert build_recall_query("Where?", ["A. X", "B. Y"], include_options=False) == "Where?"
    q = build_recall_query("Where?", ["A. X", "B. Y"], include_options=True)
    assert q.startswith("Where?")
    assert "Candidate options:" in q
    assert "A. X" in q


def test_normalize_results_filters_and_top_k():
    raw = [
        {"id": "1", "text": "Seattle", "scores": {"final": 0.9}, "mentioned_at": "2026-01-01T00:00:00Z"},
        {"id": "1", "text": "Seattle"},
        {"id": "2", "text": ""},
        {"id": "3", "text": "Seattle"},
        {"id": "4", "text": "Boston", "scores": {"final": 0.2}},
    ]
    items = _normalize_results(raw, top_k=2)
    assert len(items) == 2
    assert items[0].id == "1"
    assert items[0].score == 0.9
    assert items[1].id == "4"
    assert items[1].content == "Boston"


# --- Phase 4B — options_in_query_mode -------------------------------------


def test_build_recall_query_default_mode_append_matches_prior_behavior():
    """Default mode='append' must keep the exact prior 'raw options' behavior."""
    prior = build_recall_query("Where?", ["A. X", "B. Y"], include_options=True)
    new = build_recall_query("Where?", ["A. X", "B. Y"], include_options=True, mode="append")
    assert prior == new
    assert "A. X" in new
    assert "B. Y" in new


def test_build_recall_query_mode_none_excludes_options():
    q = build_recall_query(
        "Where?",
        ["A. Boston", "B. Seattle"],
        include_options=True,
        mode="none",
    )
    assert q == "Where?"
    assert "Boston" not in q
    assert "Candidate options" not in q


def test_build_recall_query_mode_rewrite_strips_option_letters():
    q = build_recall_query(
        "Where?",
        ["A. Boston", "(b) Seattle", "[C] Austin", "D: New York", "e) London", "Boston"],
        include_options=True,
        mode="rewrite",
    )
    # All prefixes stripped; letter itself not preserved.
    assert "- Boston" in q
    assert "- Seattle" in q
    assert "- Austin" in q
    assert "- New York" in q
    assert "- London" in q
    # No leading "A." or "(b)" left in the option lines.
    assert "A. Boston" not in q
    assert "(b) Seattle" not in q
    assert "[C] Austin" not in q
    assert "D: New York" not in q
    assert "e) London" not in q


def test_build_recall_query_mode_rewrite_drops_blank_options():
    """Blank/whitespace-only options are skipped; regex-based dropping is a subset."""
    q = build_recall_query(
        "Where?",
        ["", "   ", "B. Boston"],
        include_options=True,
        mode="rewrite",
    )
    assert "- Boston" in q
    # Only one bullet line got emitted.
    assert q.count("\n- ") == 1


def test_build_recall_query_include_false_ignores_mode():
    for mode in ("append", "none", "rewrite"):
        q = build_recall_query(
            "Where?",
            ["A. Boston"],
            include_options=False,
            mode=mode,
        )
        assert q == "Where?"
