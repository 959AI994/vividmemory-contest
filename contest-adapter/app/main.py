from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .client import (
    VividMemoryClient,
    build_recall_query,
    format_conversation_document,
    user_to_bank_id,
)
from .schemas import AddRequest, AddResponse, SearchRequest, SearchResponse, SearchResultItem
from .settings import Settings, get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("contest-adapter")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    timeout = httpx.Timeout(settings.http_timeout_seconds, connect=30.0)
    client = httpx.AsyncClient(timeout=timeout)
    app.state.settings = settings
    app.state.http = client
    app.state.vm = VividMemoryClient(settings, client)
    logger.info("adapter started base_url=%s", settings.vividmemory_base_url)
    try:
        yield
    finally:
        await client.aclose()
        logger.info("adapter stopped")


app = FastAPI(title="VividMemory Contest Adapter", version="0.1.0", lifespan=lifespan)


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _vm(request: Request) -> VividMemoryClient:
    return request.app.state.vm


@app.get("/health")
async def health(request: Request) -> JSONResponse:
    """Adapter + core API health."""
    try:
        core = await _vm(request).health()
    except Exception as exc:  # noqa: BLE001
        logger.error("core health check failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "core": "unreachable", "detail": str(exc)},
        )
    core_status = core.get("status")
    if core_status != "healthy":
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "core": core},
        )
    return JSONResponse(status_code=200, content={"status": "ok", "core": core})


@app.post("/add", response_model=AddResponse)
async def add_memories(body: AddRequest, request: Request) -> AddResponse:
    """Persist contest messages via synchronous retain."""
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    settings = _settings(request)
    bank_id = user_to_bank_id(body.user_id)

    try:
        content = format_conversation_document(
            messages=body.messages,
            request_id=body.request_id,
            session_id=body.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Prefer the latest message timestamp as the document event time.
    timestamps = [m.timestamp for m in body.messages if m.timestamp is not None]
    timestamp_iso = None
    if timestamps:
        from datetime import datetime, timezone

        latest_ms = max(timestamps)
        timestamp_iso = datetime.fromtimestamp(latest_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        await _vm(request).retain_document(
            bank_id=bank_id,
            content=content,
            document_id=body.request_id,
            session_id=body.session_id,
            timestamp_iso=timestamp_iso,
        )
    except httpx.HTTPStatusError as exc:
        logger.exception("retain HTTP error")
        raise HTTPException(
            status_code=502,
            detail=f"vividmemory retain failed: {exc.response.status_code} {exc.response.text[:500]}",
        ) from exc
    except httpx.HTTPError as exc:
        logger.exception("retain transport error")
        raise HTTPException(status_code=502, detail=f"vividmemory retain unreachable: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("retain unexpected error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _ = settings  # reserved for future adapter knobs
    return AddResponse(
        success=True,
        request_id=body.request_id,
        user_id=body.user_id,
        session_id=body.session_id,
    )


def _normalize_results(raw_results: list[dict[str, Any]], top_k: int) -> list[SearchResultItem]:
    seen_ids: set[str] = set()
    seen_content: set[str] = set()
    items: list[SearchResultItem] = []

    for row in raw_results:
        memory_id = str(row.get("id") or "").strip()
        content = str(row.get("text") or "").strip()
        if not memory_id or not content:
            continue
        if memory_id in seen_ids:
            continue
        if content in seen_content:
            continue

        score = None
        scores = row.get("scores")
        if isinstance(scores, dict) and scores.get("final") is not None:
            try:
                score = float(scores["final"])
            except (TypeError, ValueError):
                score = None

        created_at = row.get("mentioned_at") or row.get("occurred_start")
        if created_at is not None:
            created_at = str(created_at)

        seen_ids.add(memory_id)
        seen_content.add(content)
        items.append(
            SearchResultItem(
                id=memory_id,
                content=content,
                score=score,
                created_at=created_at,
            )
        )
        if len(items) >= top_k:
            break

    return items


@app.post("/search", response_model=SearchResponse)
async def search_memories(body: SearchRequest, request: Request) -> SearchResponse:
    """Search memories via recall only (never reflect)."""
    settings = _settings(request)
    bank_id = user_to_bank_id(body.user_id)
    query = build_recall_query(
        body.query,
        body.options,
        include_options=settings.include_options_in_query,
    )
    if not query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    try:
        raw = await _vm(request).recall(bank_id=bank_id, query=query, top_k=body.top_k)
    except httpx.HTTPStatusError as exc:
        # Empty bank / no results should still be a valid empty list when the
        # core API returns structured empty results. Validation errors on query
        # are mapped carefully.
        if exc.response.status_code == 422:
            logger.warning("recall validation error: %s", exc.response.text[:500])
            return SearchResponse(data=[])
        logger.exception("recall HTTP error")
        raise HTTPException(
            status_code=502,
            detail=f"vividmemory recall failed: {exc.response.status_code} {exc.response.text[:500]}",
        ) from exc
    except httpx.HTTPError as exc:
        logger.exception("recall transport error")
        raise HTTPException(status_code=502, detail=f"vividmemory recall unreachable: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("recall unexpected error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return SearchResponse(data=_normalize_results(raw, body.top_k))
