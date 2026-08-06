from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .client import (
    VividMemoryClient,
    build_recall_query,
    format_conversation_document,
    format_message_documents,
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
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    settings = _settings(request)
    bank_id = user_to_bank_id(body.user_id)

    try:
        if settings.per_message_retain:
            documents = format_message_documents(
                messages=body.messages,
                request_id=body.request_id,
                session_id=body.session_id,
            )
        else:
            content = format_conversation_document(
                messages=body.messages,
                request_id=body.request_id,
                session_id=body.session_id,
            )
            timestamps = [m.timestamp for m in body.messages if m.timestamp is not None]
            latest_ts_iso = None
            if timestamps:
                from datetime import datetime, timezone
                latest_ms = max(timestamps)
                latest_ts_iso = datetime.fromtimestamp(
                    latest_ms / 1000.0, tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            documents = [(body.request_id, content, latest_ts_iso)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    semaphore = asyncio.Semaphore(settings.retain_concurrency)
    vm = _vm(request)

    async def _one(doc_id: str, doc_content: str, ts_iso: str | None) -> None:
        async with semaphore:
            await vm.retain_document(
                bank_id=bank_id,
                content=doc_content,
                document_id=doc_id,
                session_id=body.session_id,
                timestamp_iso=ts_iso,
            )

    try:
        await asyncio.gather(*(
            _one(doc_id, doc_content, ts_iso)
            for doc_id, doc_content, ts_iso in documents
        ))
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

    return AddResponse(
        success=True,
        request_id=body.request_id,
        user_id=body.user_id,
        session_id=body.session_id,
    )


def _tokenize_for_dedup(text: str) -> frozenset[str]:
    """Lowercased alphanumeric-token set for Jaccard near-dedup."""
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def _normalize_results(
    raw_results: list[dict[str, Any]],
    top_k: int,
    *,
    near_dedup_threshold: float = 0.0,
) -> list[SearchResultItem]:
    seen_ids: set[str] = set()
    seen_content: set[str] = set()
    items: list[SearchResultItem] = []
    kept_tokens: list[frozenset[str]] = []
    dedup_active = near_dedup_threshold > 0.0

    for row in raw_results:
        memory_id = str(row.get("id") or "").strip()
        content = str(row.get("text") or "").strip()
        if not memory_id or not content:
            continue
        if memory_id in seen_ids:
            continue
        if content in seen_content:
            continue

        if dedup_active:
            tokens = _tokenize_for_dedup(content)
            if any(_jaccard(tokens, kt) >= near_dedup_threshold for kt in kept_tokens):
                continue
        else:
            tokens = frozenset()

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
        if dedup_active:
            kept_tokens.append(tokens)
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
        mode=settings.options_in_query_mode,
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

    return SearchResponse(
        data=_normalize_results(
            raw,
            body.top_k,
            near_dedup_threshold=settings.near_dedup_threshold,
        )
    )
