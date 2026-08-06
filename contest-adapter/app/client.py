from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from .schemas import Message
from .settings import Settings

logger = logging.getLogger(__name__)

# Phase 4B — used by build_recall_query(mode="rewrite") to strip leading option
# letters from candidate options. Matches an optional (/[, one ASCII letter, a
# closing punct )/]/./:, then required whitespace. Never anchor on a specific
# letter — that would risk overfitting to benchmark option schemes.
_OPTION_PREFIX_RE = re.compile(r"^\s*[\(\[]?[A-Za-z][\)\]\.\:]\s+")


def user_to_bank_id(user_id: str) -> str:
    """Map contest user_id to an isolated VividMemory bank."""
    digest = hashlib.sha256(user_id.encode("utf-8")).hexdigest()
    return f"contest-{digest}"


def _ms_to_iso(timestamp_ms: int | None) -> str | None:
    if timestamp_ms is None:
        return None
    try:
        dt = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_conversation_document(
    *,
    messages: list[Message],
    request_id: str,
    session_id: str,
) -> str:
    """Turn Add messages into one conversation document for retain."""
    lines: list[str] = [
        f"request_id: {request_id}",
        f"session_id: {session_id}",
        "",
    ]
    for msg in messages:
        ts = _ms_to_iso(msg.timestamp)
        role = (msg.role or "user").strip() or "user"
        content = (msg.content or "").strip()
        if not content:
            continue
        if ts:
            lines.append(f"{role} ({ts}): {content}")
        else:
            lines.append(f"{role}: {content}")
    body = "\n".join(lines).strip()
    if not body or body == f"request_id: {request_id}\nsession_id: {session_id}":
        raise ValueError("messages must contain at least one non-empty content field")
    return body


def format_message_documents(
    *,
    messages: list[Message],
    request_id: str,
    session_id: str,
) -> list[tuple[str, str, str | None]]:
    """One retain document per non-empty message.

    Returns list of (document_id, content, timestamp_iso). Document IDs are
    deterministic: f"{request_id}:msg:{index}" using the ORIGINAL position in
    the messages array (indexing counts empty messages, so re-sends with the
    same payload get the same IDs).
    """
    docs: list[tuple[str, str, str | None]] = []
    for idx, msg in enumerate(messages):
        content = (msg.content or "").strip()
        if not content:
            continue
        role = (msg.role or "user").strip() or "user"
        ts = _ms_to_iso(msg.timestamp)
        doc_id = f"{request_id}:msg:{idx}"
        header_lines = [
            f"request_id: {request_id}",
            f"session_id: {session_id}",
            "",
        ]
        body_line = f"{role} ({ts}): {content}" if ts else f"{role}: {content}"
        body = "\n".join(header_lines + [body_line]).strip()
        docs.append((doc_id, body, ts))
    if not docs:
        raise ValueError("messages must contain at least one non-empty content field")
    return docs


def build_recall_query(
    query: str,
    options: list[str] | None,
    *,
    include_options: bool,
    mode: Literal["append", "none", "rewrite"] = "append",
) -> str:
    q = (query or "").strip()
    if not include_options or not options or mode == "none":
        return q
    cleaned: list[str] = []
    for opt in options:
        text = str(opt or "").strip()
        if not text:
            continue
        if mode == "rewrite":
            text = _OPTION_PREFIX_RE.sub("", text).strip()
            if not text:
                continue
        cleaned.append(text)
    if not cleaned:
        return q
    option_lines = "\n".join(f"- {t}" for t in cleaned)
    return f"{q}\n\nCandidate options:\n{option_lines}"


class VividMemoryClient:
    """Thin async HTTP client for vividmemory-api-slim retain/recall."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self._settings = settings
        self._client = client
        self._base = settings.vividmemory_base_url.rstrip("/")

    async def health(self) -> dict[str, Any]:
        resp = await self._client.get(f"{self._base}/health")
        resp.raise_for_status()
        return resp.json()

    async def retain_document(
        self,
        *,
        bank_id: str,
        content: str,
        document_id: str,
        session_id: str,
        timestamp_iso: str | None,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "content": content,
            "document_id": document_id,
            "update_mode": "replace",
            "metadata": {
                "request_id": document_id,
                "session_id": session_id,
                "source": "contest-adapter",
            },
            "tags": [f"session:{session_id}"],
        }
        if timestamp_iso:
            item["timestamp"] = timestamp_iso

        payload = {"items": [item], "async": False}
        url = f"{self._base}/v1/default/banks/{bank_id}/memories"
        logger.info("retain bank=%s document_id=%s", bank_id, document_id)
        resp = await self._client.post(url, json=payload)
        if resp.status_code >= 400:
            logger.error("retain failed status=%s body=%s", resp.status_code, resp.text[:2000])
            resp.raise_for_status()
        return resp.json()

    async def recall(
        self,
        *,
        bank_id: str,
        query: str,
        top_k: int,
        types: list[str] | None = None,
        prefer_observations: bool = False,
        tags: list[str] | None = None,
        tags_match: str = "any",
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "query": query,
            "budget": self._settings.recall_budget,
            "max_tokens": self._settings.recall_max_tokens,
            "trace": False,
            "include": {"entities": None},
        }
        if types is not None:
            payload["types"] = types
        if prefer_observations:
            payload["prefer_observations"] = True
        if tags is not None:
            payload["tags"] = tags
            payload["tags_match"] = tags_match
        url = f"{self._base}/v1/default/banks/{bank_id}/memories/recall"
        logger.info("recall bank=%s top_k=%s query_len=%s", bank_id, top_k, len(query))
        resp = await self._client.post(url, json=payload)
        if resp.status_code >= 400:
            logger.error("recall failed status=%s body=%s", resp.status_code, resp.text[:2000])
            resp.raise_for_status()
        data = resp.json()
        results = data.get("results") or []
        if not isinstance(results, list):
            return []
        return results[: max(top_k * 3, top_k)]
