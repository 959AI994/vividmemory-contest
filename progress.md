# VividMemory Contest — Optimization Progress

Working branch: `perf/contest-memory-optimization`
Baseline commit: `b36ae44` (main, Fix contest Docker startup by using Compose Postgres instead of pg0.)

## 1. Objective

Raise VividMemory's score on the Agent Memory Challenge Textual Memory benchmark
by adding feature-flag-gated retrieval, extraction, and reranking improvements to
the contest adapter and engine wiring — without rewriting the core.

## 2. Repo state (initial)

- Adapter: `contest-adapter/` (FastAPI :8000, `/add`/`/search`/`/health`).
- Engine: `vividmemory-api-slim/` (Postgres + pgvector, retain/recall, ships local cross-encoder).
- Compose: three services (db, vividmemory, adapter) wired via `${VAR:-default}`.
- Tests: 4 offline unit tests + `scripts/smoke_test.sh` integration probe.
- Datasets locally present: LoCoMo (`data/locomo10.json`), ScriptMem (`data/raw/*.json`), BEAM (100K–10M).
- Untracked (gitignored): `benchmarks/`, `sota/`, `evaluation/agent-memory-leaderboard/`, `runs/`.

## 3. Evaluation contract

- Answer LLM and Judge LLM are configured **only** through env vars (`ANSWER_*` and `JUDGE_*`).
- Local-dev scores using DeepSeek/OpenAI-compatible gateway are labeled `[local-dev, deepseek-v4-pro]`.
- Official-equivalent scores (`gpt-4o-mini` + Qwen judge) are labeled `[official-equivalent]`.
- Retrieval proxy metrics (recall@k, substring-EM) computed cheaply before invoking answer/judge.

## 4. Bench availability

| Dataset | Local | HF download needed | Status |
|---|---|---|---|
| LoCoMo | ✅ `data/locomo10.json` | — | scoreable |
| ScriptMem | ✅ `data/raw/*.json` | — | scoreable |
| BEAM | ✅ 100K variant | — | scoreable |
| CL-bench | ❌ | ✅ (deferred) | not-scored-locally |
| LongMemEval-S | ❌ | ✅ (deferred) | not-scored-locally |
| PersonaMem | ❌ | ✅ (deferred) | not-scored-locally |

## 5. Baseline configuration

- Branch commit: `f2ba8c8` (Phase 0.2 runner skeleton) — pending baseline run
- Adapter flags: all defaults (see `.env.example`)
- LLM: `gpt-4o-mini` (or gateway equivalent per `.env`)
- Embed: `text-embedding-3-small`
- Rerank: `rrf` (passthrough)

## 6. Baseline results

_Pending. Populated after running:_

```
python -m evaluation.vividmemory_runner.run full \
    --config evaluation/vividmemory_runner/configs/dev.yaml \
    --run-id baseline_$(date +%Y%m%d_%H%M)
```

## 7. Experiment table

| # | Phase | Flag change | Dataset(s) | Proxy metric Δ | Judge score Δ | Latency Δ | Status |
|---|---|---|---|---|---|---|---|
| 0.1 | 0 | branch + gitignore + progress.md | — | n/a | n/a | n/a | landed `94e3dba` |
| 0.3 | 0 | env vars + Compose wiring (no behavior change) | — | 0 | 0 | 0 | landed `da425f7`, followup `9e2b2ab` |
| 2   | 0 | adapter settings + schema additions | — | 0 | 0 | 0 | landed `3e0bb50`, tightened `ccc1e30` |
| 1   | 1 | `ADAPTER_PER_MESSAGE_RETAIN` (flag off by default) | LoCoMo (targeted) | pending | pending | pending | landed `2133068` |
| 4B  | 4 | `ADAPTER_OPTIONS_IN_QUERY_MODE` append/none/rewrite | BEAM/CL-Bench (MCQ) | pending | pending | pending | landed `78a1896` |
| 4C  | 4 | `ADAPTER_NEAR_DEDUP_THRESHOLD` token-Jaccard collapse | all | pending | pending | pending | landed `2d36b41` |
| 3   | 3 | `ADAPTER_RECALL_INCLUDE_OBSERVATIONS` + `ADAPTER_EPISODE_PREPEND` | ScriptMem, LoCoMo | pending | pending | pending | landed `91f2a4f` |
| 2   | 2 | custom-extraction prompt file + `enable_contest_extraction.sh` | LongMemEval-like | pending | pending | pending | landed `bf3c2ce` |
| 4A  | 4 | `enable_local_reranker.sh` helper (wiring only) | all | pending | pending | pending | landed `dd92ab0` |
| 0.2 | 0 | benchmark runner skeleton (LoCoMo ingest/search/proxy) | LoCoMo dev | pending | n/a | pending | landed `f2ba8c8` |
| 5   | 5 | runner client exponential backoff + jitter | all | 0 (reliability) | 0 | 0 | landed `9dc6021` |

## 8. Per-dataset table

| Dataset | Baseline | Best | Best flags | Label |
|---|---|---|---|---|

_Pending baseline measurement._

## 9. Failed experiments (kept behind disabled flag or reverted)

_Pending._

## 10. Current best

Flag set:

```
# defaults — no changes yet
```

## 11. Risks

- CL-Bench / LongMemEval / PersonaMem require HF downloads; deferred.
- Cross-encoder rerank adds first-run download; may need Dockerfile pre-fetch step.
- Prompt tuning must not touch benchmark gold answers.

## 12. Next actions

1. Land Phase 0.1 (repo hygiene, branch, progress.md).
2. Land Phase 0.3 (env schema + Compose wiring for all future flags — behavior unchanged).
3. Land Phase 0.2 (benchmark runner skeleton).
4. Land Phase 0.4 (baseline measurement).
5. Roll through Phases 1 → 5, one flag at a time.
6. Phase 6 finalize + reproducible submission.

## 13. Command log

```
$ git switch -c perf/contest-memory-optimization
```
