"""LoCoMo dataset adapter for the runner.

Ingests each LoCoMo conversation as a single user's memory bank. All messages
across all sessions become one long chat log for that user. Each session's
messages share a session_id derived from the session index.

Query records preserve the gold answer and the raw evidence texts, so
proxy recall@k can be computed from the /search response.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ConversationRecord, QueryRecord, TurnRecord

logger = logging.getLogger(__name__)

# LoCoMo timestamps look like "1:56 pm on 8 May, 2023"
_LOCOMO_TS_RE = re.compile(
    r"^\s*(?P<hour>\d{1,2}):(?P<min>\d{2})\s*(?P<ampm>am|pm)\s+on\s+"
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+),?\s+(?P<year>\d{4})",
    re.IGNORECASE,
)
_MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["january", "february", "march", "april", "may", "june", "july",
         "august", "september", "october", "november", "december"]
    )
}


def _parse_locomo_ts(text: str | None) -> int | None:
    if not text:
        return None
    m = _LOCOMO_TS_RE.match(text)
    if not m:
        return None
    hour = int(m["hour"]) % 12
    if m["ampm"].lower() == "pm":
        hour += 12
    month = _MONTHS.get(m["month"].lower())
    if month is None:
        return None
    try:
        dt = datetime(
            year=int(m["year"]),
            month=month,
            day=int(m["day"]),
            hour=hour,
            minute=int(m["min"]),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)


def load_locomo(
    *,
    path: str | Path,
    run_id: str,
    max_conversations: int | None = None,
    max_questions_per_conversation: int | None = None,
) -> tuple[list[ConversationRecord], list[QueryRecord]]:
    """Return (conversations, queries) ready for ingest + search."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    convs: list[ConversationRecord] = []
    queries: list[QueryRecord] = []

    conv_list = raw if max_conversations is None else raw[:max_conversations]
    for conv_idx, item in enumerate(conv_list):
        conv_body: dict[str, Any] = item.get("conversation", {})
        speaker_a = conv_body.get("speaker_a", "speaker_a")
        speaker_b = conv_body.get("speaker_b", "speaker_b")
        sample_id = item.get("sample_id") or f"locomo:{conv_idx}"
        conv_id = f"{sample_id}"

        # Build a lookup dia_id -> text for evidence resolution.
        dia_lookup: dict[str, str] = {}

        # Collect all turns across all sessions in chronological order.
        turns: list[TurnRecord] = []
        session_ids: list[str] = []
        session_idx = 1
        while True:
            sess_key = f"session_{session_idx}"
            ts_key = f"session_{session_idx}_date_time"
            if sess_key not in conv_body:
                break
            session_turns = conv_body.get(sess_key) or []
            session_ts_str = conv_body.get(ts_key)
            base_ts = _parse_locomo_ts(session_ts_str)
            session_id = f"eval:{run_id}:locomo:{conv_id}:s{session_idx}"
            session_ids.append(session_id)
            for turn_i, t in enumerate(session_turns):
                speaker = t.get("speaker") or ""
                text = t.get("text") or ""
                dia_id = t.get("dia_id") or ""
                if dia_id and text:
                    dia_lookup[dia_id] = text
                if not text:
                    continue
                role = "user" if speaker == speaker_a else "assistant"
                ts_ms = base_ts + turn_i * 1000 if base_ts is not None else None
                turns.append(
                    TurnRecord(
                        role=role,
                        content=f"{speaker}: {text}",
                        timestamp_ms=ts_ms,
                    )
                )
            session_idx += 1

        if not turns:
            continue

        # Single user_id per conversation (both speakers folded into one bank
        # because /search is asked for facts about either speaker).
        speaker_key = "conv"
        user_id = f"eval:{run_id}:locomo:{conv_id}:{speaker_key}"
        primary_session_id = session_ids[0] if session_ids else f"eval:{run_id}:locomo:{conv_id}"
        convs.append(
            ConversationRecord(
                conversation_id=conv_id,
                speaker_key=speaker_key,
                turns=turns,
                session_id=primary_session_id,
                metadata={
                    "speaker_a": speaker_a,
                    "speaker_b": speaker_b,
                    "user_id": user_id,
                    "num_turns": len(turns),
                },
            )
        )

        qa_list = item.get("qa") or []
        if max_questions_per_conversation is not None:
            qa_list = qa_list[:max_questions_per_conversation]
        for q_idx, q in enumerate(qa_list):
            question = str(q.get("question") or "").strip()
            if not question:
                continue
            answer = q.get("answer")
            evidence_ids = q.get("evidence") or []
            evidence_texts = [
                dia_lookup[e] for e in evidence_ids if e in dia_lookup
            ]
            queries.append(
                QueryRecord(
                    query_id=f"{conv_id}:q{q_idx}",
                    conversation_id=conv_id,
                    speaker_key=speaker_key,
                    query=question,
                    gold_answer=None if answer is None else str(answer),
                    evidence_texts=evidence_texts,
                    session_id=primary_session_id,
                    metadata={
                        "user_id": user_id,
                        "category": q.get("category"),
                        "evidence_ids": evidence_ids,
                    },
                )
            )

    logger.info(
        "loaded locomo: %d conversations, %d queries",
        len(convs),
        len(queries),
    )
    return convs, queries
