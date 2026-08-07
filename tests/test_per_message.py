"""Tests for per-message retain formatting (Phase 1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contest-adapter"))

from app.client import (  # noqa: E402
    _ms_to_iso,
    format_conversation_document,
    format_message_documents,
)
from app.schemas import Message  # noqa: E402


def test_format_conversation_document_single_message_unchanged():
    ts_ms = 1704067200000
    msg = Message(role="user", content="I live in Boston.", timestamp=ts_ms)
    doc = format_conversation_document(
        messages=[msg],
        request_id="req-1",
        session_id="sess-1",
    )
    ts_iso = _ms_to_iso(ts_ms)
    expected = (
        f"request_id: req-1\n"
        f"session_id: sess-1\n"
        f"\n"
        f"user ({ts_iso}): I live in Boston."
    )
    assert doc == expected


def test_format_message_documents_creates_one_per_message():
    rid = "req-multi"
    msgs = [
        Message(role="user", content="A", timestamp=1704067200000),
        Message(role="assistant", content="B", timestamp=1704067201000),
        Message(role="user", content="C", timestamp=1704067202000),
    ]
    docs = format_message_documents(messages=msgs, request_id=rid, session_id="sess-x")
    assert len(docs) == 3
    ids = [d[0] for d in docs]
    assert ids == [f"{rid}:msg:0", f"{rid}:msg:1", f"{rid}:msg:2"]


def test_format_message_documents_empty_content_uses_original_index():
    rid = "req-empty"
    msgs = [
        Message(role="user", content="A", timestamp=1704067200000),
        Message(role="user", content="", timestamp=1704067201000),
        Message(role="user", content="B", timestamp=1704067202000),
    ]
    docs = format_message_documents(messages=msgs, request_id=rid, session_id="sess-y")
    assert len(docs) == 2
    ids = [d[0] for d in docs]
    assert ids == [f"{rid}:msg:0", f"{rid}:msg:2"]


def test_format_message_documents_per_message_timestamp():
    rid = "req-ts"
    msgs = [
        Message(role="user", content="A", timestamp=1704067200000),
        Message(role="user", content="B", timestamp=1706745600000),
        Message(role="user", content="C", timestamp=1709251200000),
    ]
    docs = format_message_documents(messages=msgs, request_id=rid, session_id="sess-z")
    assert len(docs) == 3
    for doc, msg in zip(docs, msgs):
        assert doc[2] == _ms_to_iso(msg.timestamp)


def test_format_message_documents_all_empty_raises():
    msgs = [
        Message(role="user", content="", timestamp=1704067200000),
        Message(role="user", content="   ", timestamp=1704067201000),
    ]
    with pytest.raises(ValueError):
        format_message_documents(messages=msgs, request_id="req-none", session_id="sess-none")


def test_format_message_documents_no_timestamp_ok():
    rid = "req-nots"
    msgs = [
        Message(role="user", content="Hello world"),
    ]
    docs = format_message_documents(messages=msgs, request_id=rid, session_id="sess-nots")
    assert len(docs) == 1
    doc_id, body, ts_iso = docs[0]
    assert doc_id == f"{rid}:msg:0"
    assert ts_iso is None
    # body should use the "role: content" form (no ISO parenthetical)
    assert "user: Hello world" in body
    assert "user (" not in body
