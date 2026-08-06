"""Thin async HTTP client for the contest adapter's /add /search /health.

Includes bounded exponential backoff on 429/5xx and transport errors.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class AdapterClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 300.0,
        *,
        max_retries: int = 4,
        base_backoff: float = 0.5,
        max_backoff: float = 10.0,
    ):
        self._base = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=30.0))
        self._max_retries = max_retries
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Retry with exponential backoff + jitter on 429/5xx or transport errors."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                resp = await self._client.request(method, url, **kwargs)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    raise
                delay = min(self._base_backoff * (2 ** attempt), self._max_backoff)
                delay = delay * (0.5 + random.random())  # jitter
                logger.warning(
                    "transport error on %s %s (attempt %d/%d): %s — sleeping %.2fs",
                    method,
                    url,
                    attempt + 1,
                    self._max_retries + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            if resp.status_code in _RETRY_STATUS and attempt < self._max_retries:
                delay = min(self._base_backoff * (2 ** attempt), self._max_backoff)
                delay = delay * (0.5 + random.random())
                logger.warning(
                    "retryable status %s on %s %s (attempt %d/%d) — sleeping %.2fs",
                    resp.status_code,
                    method,
                    url,
                    attempt + 1,
                    self._max_retries + 1,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            resp.raise_for_status()
            return resp

        # Exhausted retries via exception path (already re-raised) — this
        # branch is unreachable but keeps mypy happy.
        assert last_exc is not None
        raise last_exc

    async def health(self) -> dict[str, Any]:
        resp = await self._request("GET", f"{self._base}/health")
        return resp.json()

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
        resp = await self._request("POST", f"{self._base}/add", json=payload)
        return resp.json()

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
        resp = await self._request("POST", f"{self._base}/search", json=payload)
        return resp.json()
