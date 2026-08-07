"""Thin driver that runs the official LoCoMo-refined answer + evaluate stages
using the leaderboard's prompt templates verbatim, but with correct file I/O
and bounded concurrency.

Rationale: evaluation/agent-memory-leaderboard/locomo-refined/pipeline.py uses
`async with output.open(...)` which is a bug in the public release (sync file
handle in an async-with clause). We import its prompt-rendering functions and
label parser so the measurement stays byte-identical to the official contract.

Reads ANSWER_* and JUDGE_* from environment (identical routing to the official
pipeline via api_config.py).
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("official_pipeline")


def _load_pipeline_module() -> Any:
    """Import the leaderboard's locomo-refined/pipeline.py by file path,
    since its parent dir is not on sys.path and has a hyphen in its name.
    """
    here = Path(__file__).resolve()
    leaderboard = here.parents[1] / "agent-memory-leaderboard"
    pipeline_path = leaderboard / "locomo-refined" / "pipeline.py"
    if not pipeline_path.exists():
        raise SystemExit(f"leaderboard pipeline not found at {pipeline_path}")
    # api_config lives one directory up; put that on sys.path so the pipeline
    # module can `from api_config import ...` at import time.
    sys.path.insert(0, str(leaderboard))
    spec = importlib.util.spec_from_file_location("locomo_pipeline", pipeline_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


async def _complete(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
) -> str:
    resp = await client.post(
        base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        },
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


async def _bounded(
    coros: list, concurrency: int
) -> list:
    sem = asyncio.Semaphore(concurrency)

    async def wrap(coro):
        async with sem:
            return await coro

    return await asyncio.gather(*(wrap(c) for c in coros))


async def run_answer(
    *, module, input_path: Path, output_path: Path, concurrency: int
) -> None:
    from api_config import ANSWER_API_BASE, ANSWER_API_KEY, ANSWER_MODEL  # type: ignore

    if not ANSWER_API_BASE or not ANSWER_API_KEY or not ANSWER_MODEL:
        raise SystemExit("ANSWER_API_BASE / ANSWER_API_KEY / ANSWER_MODEL must be set")

    items = module.rows(str(input_path))
    done = {r.get("id") for r in module.rows(str(output_path))} if output_path.exists() else set()
    todo = [it for it in items if it["id"] not in done]
    logger.info("answer: %d items, %d already done, %d to go", len(items), len(done), len(todo))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=900) as client:

        async def one(item: dict[str, Any]) -> dict[str, Any]:
            prompt = module.render_answer_prompt(item)
            try:
                generated = await _complete(
                    client,
                    base_url=ANSWER_API_BASE,
                    api_key=ANSWER_API_KEY,
                    model=ANSWER_MODEL,
                    prompt=prompt,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("answer failed for %s: %s", item["id"], exc)
                return {"id": item["id"], "generated_answer": "", "error": str(exc)}
            return {"id": item["id"], "generated_answer": generated}

        results = await _bounded([one(it) for it in todo], concurrency)

    with output_path.open("a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


async def run_evaluate(
    *,
    module,
    input_path: Path,
    answers_path: Path,
    output_path: Path,
    concurrency: int,
) -> None:
    from api_config import JUDGE_API_BASE, JUDGE_API_KEY, JUDGE_MODEL  # type: ignore

    if not JUDGE_API_BASE or not JUDGE_API_KEY or not JUDGE_MODEL:
        raise SystemExit("JUDGE_API_BASE / JUDGE_API_KEY / JUDGE_MODEL must be set")

    items = {it["id"]: it for it in module.rows(str(input_path))}
    answers = {r["id"]: r["generated_answer"] for r in module.rows(str(answers_path))}
    if set(items) != set(answers):
        missing = set(items) - set(answers)
        extra = set(answers) - set(items)
        raise SystemExit(f"input/answer id mismatch — missing={missing}, extra={extra}")

    logger.info("evaluate: %d items", len(items))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=900) as client:

        async def judge_one(ident: str) -> dict[str, Any]:
            item = items[ident]
            prompt = module.render_accuracy_prompt(item, answers[ident])
            try:
                resp = await _complete(
                    client,
                    base_url=JUDGE_API_BASE,
                    api_key=JUDGE_API_KEY,
                    model=JUDGE_MODEL,
                    prompt=prompt,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("judge call failed for %s: %s", ident, exc)
                return {
                    "id": ident,
                    "label": "WRONG",
                    "is_correct": False,
                    "judge_response": "",
                    "error": str(exc),
                }
            try:
                label = module.parse_judge_label(resp)
            except Exception as exc:  # noqa: BLE001
                logger.warning("judge parse failed for %s: %s", ident, exc)
                label = "WRONG"
            return {
                "id": ident,
                "label": label,
                "is_correct": label == "CORRECT",
                "judge_response": resp,
            }

        results = await _bounded([judge_one(i) for i in items], concurrency)

    with output_path.open("w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def compute_score(scores_path: Path) -> dict[str, Any]:
    """Aggregate CORRECT/WRONG labels into an accuracy score."""
    rows: list[dict] = []
    with scores_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    n = len(rows)
    correct = sum(1 for r in rows if r.get("is_correct"))
    return {
        "num_questions": n,
        "num_correct": correct,
        "accuracy": (correct / n) if n else 0.0,
        "accuracy_pct": round((correct / n) * 100, 2) if n else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("answer")
    a.add_argument("--input", required=True)
    a.add_argument("--output", required=True)
    a.add_argument("--concurrency", type=int, default=8)

    e = sub.add_parser("evaluate")
    e.add_argument("--input", required=True)
    e.add_argument("--answers", required=True)
    e.add_argument("--output", required=True)
    e.add_argument("--concurrency", type=int, default=8)

    s = sub.add_parser("score")
    s.add_argument("--scores", required=True)

    args = ap.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    module = _load_pipeline_module()

    if args.cmd == "answer":
        asyncio.run(
            run_answer(
                module=module,
                input_path=Path(args.input),
                output_path=Path(args.output),
                concurrency=args.concurrency,
            )
        )
    elif args.cmd == "evaluate":
        asyncio.run(
            run_evaluate(
                module=module,
                input_path=Path(args.input),
                answers_path=Path(args.answers),
                output_path=Path(args.output),
                concurrency=args.concurrency,
            )
        )
    elif args.cmd == "score":
        result = compute_score(Path(args.scores))
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
