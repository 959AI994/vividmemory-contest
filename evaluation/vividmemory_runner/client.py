"""Thin async HTTP client for the contest adapter's /add /search /health."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AdapterClient:
    def __init__(self, base_url: str, timeout: float = 300.0):
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0))

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict[str, Any]:
        r = await self._client.get(f"{self._base}/health")
        r.raise_for_status()
        return r.json()

    async def add(
        self,
        *,
        request_id: str,
        user_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = {
            "request_id": request_id,
            "user_id": user_id,
            "session_id": session_id,
            "messages": messages,
        }
        r = await self._client.post(f"{self._base}/add", json=payload)
        r.raise_for_status()
        return r.json()

    async def search(
        self,
        *,
        query: str,
        user_id: str,
        top_k: int = 10,
        session_id: str | None = None,
        options: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query, "user_id": user_id, "top_k": top_k}
        if session_id is not None:
            payload["session_id"] = session_id
        if options is not None:
            payload["options"] = options
        r = await self._client.post(f"{self._base}/search", json=payload)
        r.raise_for_status()
        return r.json()
