"""Runner CLI: ingest / search / proxy / full."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from .adapters.locomo import load_locomo
from .checkpointing import append_jsonl, load_completed_keys
from .client import AdapterClient
from .config import DatasetConfig, RunConfig
from .proxy import recall_at_k

logger = logging.getLogger("vividmemory_runner")

# Dataset name -> loader
_LOADERS = {
    "locomo": load_locomo,
}


def _runs_dir(run_id: str, dataset: str) -> Path:
    root = Path("runs") / run_id / dataset
    root.mkdir(parents=True, exist_ok=True)
    return root


async def _ingest_one(
    client: AdapterClient,
    *,
    conv,
    run_id: str,
    dataset: str,
    sem: asyncio.Semaphore,
    ckpt_path: Path,
    already_done: set[str],
) -> dict[str, Any] | None:
    request_id = f"eval:{run_id}:{dataset}:{conv.conversation_id}:{conv.speaker_key}:0"
    if request_id in already_done:
        return None
    user_id = conv.metadata.get("user_id") or f"eval:{run_id}:{dataset}:{conv.conversation_id}:{conv.speaker_key}"
    session_id = conv.session_id or f"eval:{run_id}:{dataset}:{conv.conversation_id}"
    messages = [
        {"role": t.role, "content": t.content, "timestamp": t.timestamp_ms}
        for t in conv.turns
    ]
    async with sem:
        t0 = time.monotonic()
        try:
            await client.add(
                request_id=request_id,
                user_id=user_id,
                session_id=session_id,
                messages=messages,
            )
            elapsed = time.monotonic() - t0
            rec = {
                "request_id": request_id,
                "conversation_id": conv.conversation_id,
                "speaker_key": conv.speaker_key,
                "user_id": user_id,
                "session_id": session_id,
                "num_messages": len(messages),
                "elapsed_seconds": elapsed,
                "status": "ok",
            }
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            rec = {
                "request_id": request_id,
                "conversation_id": conv.conversation_id,
                "speaker_key": conv.speaker_key,
                "user_id": user_id,
                "session_id": session_id,
                "num_messages": len(messages),
                "elapsed_seconds": elapsed,
                "status": "error",
                "error": repr(exc),
            }
    append_jsonl(ckpt_path, [rec])
    return rec


async def cmd_ingest(cfg: RunConfig, run_id: str) -> None:
    client = AdapterClient(cfg.adapter_base_url, cfg.request_timeout_seconds)
    try:
        await client.health()
        for ds in cfg.datasets:
            loader = _LOADERS.get(ds.name)
            if loader is None:
                logger.warning("no loader for dataset '%s' — skipping", ds.name)
                continue
            convs, _queries = loader(
                path=ds.path,
                run_id=run_id,
                max_conversations=ds.max_conversations,
                max_questions_per_conversation=ds.max_questions_per_conversation,
            )
            out_dir = _runs_dir(run_id, ds.name)
            ckpt = out_dir / "add_checkpoint.jsonl"
            done = load_completed_keys(ckpt, "request_id")
            sem = asyncio.Semaphore(cfg.add_concurrency)
            logger.info(
                "%s: ingesting %d conversations (already done=%d)",
                ds.name,
                len(convs),
                len(done),
            )
            await asyncio.gather(
                *(
                    _ingest_one(
                        client,
                        conv=c,
                        run_id=run_id,
                        dataset=ds.name,
                        sem=sem,
                        ckpt_path=ckpt,
                        already_done=done,
                    )
                    for c in convs
                )
            )
    finally:
        await client.close()


async def _search_one(
    client: AdapterClient,
    *,
    q,
    top_k: int,
    sem: asyncio.Semaphore,
    ckpt_path: Path,
    already_done: set[str],
) -> dict[str, Any] | None:
    if q.query_id in already_done:
        return None
    user_id = q.metadata.get("user_id") or ""
    async with sem:
        t0 = time.monotonic()
        try:
            resp = await client.search(
                query=q.query,
                user_id=user_id,
                top_k=top_k,
                session_id=q.session_id,
                options=q.options,
            )
            elapsed = time.monotonic() - t0
            items = resp.get("data") or []
            rec = {
                "query_id": q.query_id,
                "conversation_id": q.conversation_id,
                "speaker_key": q.speaker_key,
                "user_id": user_id,
                "session_id": q.session_id,
                "query": q.query,
                "gold_answer": q.gold_answer,
                "evidence_texts": q.evidence_texts,
                "results": items,
                "elapsed_seconds": elapsed,
                "status": "ok",
            }
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            rec = {
                "query_id": q.query_id,
                "conversation_id": q.conversation_id,
                "speaker_key": q.speaker_key,
                "user_id": user_id,
                "session_id": q.session_id,
                "query": q.query,
                "gold_answer": q.gold_answer,
                "evidence_texts": q.evidence_texts,
                "results": [],
                "elapsed_seconds": elapsed,
                "status": "error",
                "error": repr(exc),
            }
    append_jsonl(ckpt_path, [rec])
    return rec


async def cmd_search(cfg: RunConfig, run_id: str) -> None:
    client = AdapterClient(cfg.adapter_base_url, cfg.request_timeout_seconds)
    try:
        await client.health()
        for ds in cfg.datasets:
            loader = _LOADERS.get(ds.name)
            if loader is None:
                logger.warning("no loader for dataset '%s' — skipping", ds.name)
                continue
            _convs, queries = loader(
                path=ds.path,
                run_id=run_id,
                max_conversations=ds.max_conversations,
                max_questions_per_conversation=ds.max_questions_per_conversation,
            )
            out_dir = _runs_dir(run_id, ds.name)
            ckpt = out_dir / "search_checkpoint.jsonl"
            done = load_completed_keys(ckpt, "query_id")
            sem = asyncio.Semaphore(cfg.search_concurrency)
            logger.info(
                "%s: searching %d queries (already done=%d)",
                ds.name,
                len(queries),
                len(done),
            )
            await asyncio.gather(
                *(
                    _search_one(
                        client,
                        q=q,
                        top_k=cfg.top_k,
                        sem=sem,
                        ckpt_path=ckpt,
                        already_done=done,
                    )
                    for q in queries
                )
            )
    finally:
        await client.close()


def cmd_proxy(cfg: RunConfig, run_id: str) -> None:
    """Compute cheap proxy metrics from search_checkpoint.jsonl. No network."""
    from .checkpointing import read_jsonl

    summary: dict[str, Any] = {"run_id": run_id, "datasets": {}}
    for ds in cfg.datasets:
        out_dir = _runs_dir(run_id, ds.name)
        search_ckpt = out_dir / "search_checkpoint.jsonl"
        if not search_ckpt.exists():
            logger.warning("no search checkpoint for %s at %s", ds.name, search_ckpt)
            continue

        proxy_rows: list[dict[str, Any]] = []
        total = 0
        recall_sum = 0.0
        with_evidence = 0
        errors = 0
        latencies: list[float] = []
        for rec in read_jsonl(search_ckpt):
            total += 1
            if rec.get("status") == "error":
                errors += 1
                continue
            latencies.append(float(rec.get("elapsed_seconds") or 0.0))
            ev = rec.get("evidence_texts") or []
            contents = [
                str(r.get("content") or "") for r in (rec.get("results") or [])
            ]
            if ev:
                with_evidence += 1
                r_at_k = recall_at_k(ev, contents)
            else:
                r_at_k = 0.0
            recall_sum += r_at_k
            proxy_rows.append(
                {
                    "query_id": rec.get("query_id"),
                    "recall_at_k": r_at_k,
                    "num_evidence": len(ev),
                    "num_results": len(contents),
                }
            )

        proxy_path = out_dir / "proxy.jsonl"
        # Rewrite the proxy file each run so it stays consistent.
        proxy_path.unlink(missing_ok=True)
        append_jsonl(proxy_path, proxy_rows)

        mean_recall = (recall_sum / with_evidence) if with_evidence > 0 else 0.0
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)
        p50 = latencies_sorted[n // 2] if n else 0.0
        p95 = latencies_sorted[int(n * 0.95)] if n else 0.0
        summary["datasets"][ds.name] = {
            "num_queries": total,
            "num_with_evidence": with_evidence,
            "errors": errors,
            "mean_recall_at_k": mean_recall,
            "search_p50_seconds": p50,
            "search_p95_seconds": p95,
        }

    summary_path = Path("runs") / run_id / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    import json

    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    logger.info("wrote %s", summary_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VividMemory contest benchmark runner")
    parser.add_argument(
        "command",
        choices=["health", "ingest", "search", "proxy", "full"],
    )
    parser.add_argument("--config", required=True, help="path to YAML config")
    parser.add_argument(
        "--run-id",
        default=None,
        help="run identifier (default: random uuid4-8)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    cfg = RunConfig.from_yaml(args.config)
    run_id = args.run_id or f"run_{uuid.uuid4().hex[:8]}"
    logger.info("run_id=%s", run_id)

    if args.command == "health":
        async def _h():
            client = AdapterClient(cfg.adapter_base_url, cfg.request_timeout_seconds)
            try:
                h = await client.health()
                print(h)
            finally:
                await client.close()
        asyncio.run(_h())
    elif args.command == "ingest":
        asyncio.run(cmd_ingest(cfg, run_id))
    elif args.command == "search":
        asyncio.run(cmd_search(cfg, run_id))
    elif args.command == "proxy":
        cmd_proxy(cfg, run_id)
    elif args.command == "full":
        asyncio.run(cmd_ingest(cfg, run_id))
        asyncio.run(cmd_search(cfg, run_id))
        cmd_proxy(cfg, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
