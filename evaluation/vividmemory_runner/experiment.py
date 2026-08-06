"""Experiment orchestrator — re-searches the same 60 baseline queries against
the already-ingested bank, then answer + evaluate against the deepseek judge.

Reuses the baseline ingest (identified by --baseline-run-id) so /add is not
re-called. Only the /search step re-runs, followed by enrich + answer + judge.

Used to A/B test adapter/engine feature flags cheaply. For ingest-side flags
(Phase 1, 2), the full runner must be used with a fresh run_id — this driver
is for search-side flags only.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from .client import AdapterClient

logger = logging.getLogger("experiment")


async def _search_one(
    client: AdapterClient,
    *,
    q_rec: dict,
    top_k: int,
    sem: asyncio.Semaphore,
) -> dict:
    """Re-search using the query, user_id, session_id, gold_answer, evidence_texts
    from the baseline search_checkpoint.jsonl row.
    """
    user_id = q_rec.get("user_id") or ""
    async with sem:
        t0 = time.monotonic()
        try:
            resp = await client.search(
                query=q_rec["query"],
                user_id=user_id,
                top_k=top_k,
                session_id=q_rec.get("session_id"),
            )
            elapsed = time.monotonic() - t0
            items = resp.get("data") or []
            return {
                "query_id": q_rec["query_id"],
                "conversation_id": q_rec.get("conversation_id"),
                "speaker_key": q_rec.get("speaker_key"),
                "user_id": user_id,
                "session_id": q_rec.get("session_id"),
                "query": q_rec["query"],
                "gold_answer": q_rec.get("gold_answer"),
                "evidence_texts": q_rec.get("evidence_texts") or [],
                "results": items,
                "elapsed_seconds": elapsed,
                "status": "ok",
            }
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            return {
                "query_id": q_rec["query_id"],
                "conversation_id": q_rec.get("conversation_id"),
                "speaker_key": q_rec.get("speaker_key"),
                "user_id": user_id,
                "session_id": q_rec.get("session_id"),
                "query": q_rec["query"],
                "gold_answer": q_rec.get("gold_answer"),
                "evidence_texts": q_rec.get("evidence_texts") or [],
                "results": [],
                "elapsed_seconds": elapsed,
                "status": "error",
                "error": repr(exc),
            }


async def run_search(
    *,
    baseline_search: Path,
    output: Path,
    adapter_url: str,
    top_k: int,
    concurrency: int,
) -> None:
    with baseline_search.open(encoding="utf-8") as f:
        baseline = [json.loads(line) for line in f if line.strip()]
    logger.info("re-searching %d queries", len(baseline))

    client = AdapterClient(adapter_url, timeout=600.0)
    try:
        h = await client.health()
        logger.info("adapter health: %s", h.get("status"))
        sem = asyncio.Semaphore(concurrency)
        recs = await asyncio.gather(
            *[
                _search_one(client, q_rec=r, top_k=top_k, sem=sem)
                for r in baseline
            ]
        )
    finally:
        await client.close()

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    errors = sum(1 for r in recs if r.get("status") == "error")
    lats = sorted(float(r.get("elapsed_seconds") or 0.0) for r in recs)
    n = len(lats) or 1
    logger.info(
        "wrote %d rows (errors=%d, p50=%.3fs, p95=%.3fs) -> %s",
        len(recs),
        errors,
        lats[n // 2],
        lats[int(n * 0.95)] if n > 1 else lats[-1],
        output,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-search", required=True, help="baseline search_checkpoint.jsonl")
    ap.add_argument("--output", required=True, help="new search_checkpoint.jsonl for this experiment")
    ap.add_argument("--adapter-url", default="http://localhost:8000")
    ap.add_argument("--top-k", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    asyncio.run(
        run_search(
            baseline_search=Path(args.baseline_search),
            output=Path(args.output),
            adapter_url=args.adapter_url,
            top_k=args.top_k,
            concurrency=args.concurrency,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
