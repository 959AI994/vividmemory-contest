"""Visibility / sync semantics documented as unit expectations.

Live sync visibility is covered by scripts/smoke_test.sh against a running stack.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "contest-adapter"))

from app.client import format_conversation_document  # noqa: E402
from app.schemas import Message  # noqa: E402


def test_add_payload_becomes_single_retain_document():
    """Contest /add maps one request to one retain item (document_id=request_id)."""
    doc = format_conversation_document(
        messages=[Message(role="user", content="Alice moved to Seattle.", timestamp=1)],
        request_id="eval:run:chunk-0",
        session_id="eval:run:session-0",
    )
    assert "Alice moved to Seattle." in doc
    assert "eval:run:chunk-0" in doc
