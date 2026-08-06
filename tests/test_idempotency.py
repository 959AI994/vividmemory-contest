"""Idempotency expectations for document_id = request_id + update_mode=replace."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contest-adapter"))

from app.client import format_conversation_document  # noqa: E402
from app.schemas import Message  # noqa: E402


def test_same_request_id_produces_identical_document_body():
    msgs = [Message(role="user", content="Alice lives in Seattle.", timestamp=1000)]
    a = format_conversation_document(messages=msgs, request_id="same-id", session_id="s1")
    b = format_conversation_document(messages=msgs, request_id="same-id", session_id="s1")
    assert a == b
