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

- Branch commit: `2f0c690` (Phase 6 docs) — first end-to-end measurement below
- Adapter flags: all defaults (see `.env.example`)
- LLM: OpenAI-compatible gateway (`deepseek-v4-pro` via local dev endpoint) — labeled **[local-dev, deepseek-v4-pro]**
- Embed: `onnx` (bge-small default; downloaded on first run)
- Rerank: `rrf` (passthrough)
- Runner config: `evaluation/vividmemory_runner/configs/dev.yaml`
  (3 LoCoMo conversations × 20 questions each = 60 queries; only LoCoMo has an adapter today)

## 6. Baseline results

**Run:** `dev_baseline_20260806_204940` (LoCoMo dev subset, defaults, no experimental flags)

Ingest (3 conversations, single-doc mode, `ADAPTER_RETAIN_CONCURRENCY=4`):

| conv_id | turns | status | ingest seconds |
|---|---|---|---|
| conv-30 | 369 | ok | 165.4 |
| conv-41 | 663 | ok | 368.1 |
| conv-26 | 419 | ok | 388.3 |
| **mean** | 484 | **3/3 ok** | **307.3** |

Search (60 queries, all returned `data`, 0 errors):

- `search_p50_seconds`: **0.702**
- `search_p95_seconds`: **1.012**

Proxy metric (substring OR Jaccard≥0.5 recall@10 vs LoCoMo evidence texts):

- **`mean_recall_at_k` = 0.000** (0 of 60 queries hit).

**Interpretation.** The proxy is intentionally cheap and strict. LoCoMo `evidence`
strings are raw conversational quotes (e.g. `"Lost my job as a banker yesterday…"`);
VividMemory stores *paraphrased extracted facts* (e.g. `"Jon lost his job… decided to
start his own business"`). Neither substring nor token-Jaccard≥0.5 catches
paraphrase equivalence, so a fact-extraction memory naturally scores near-zero on
this proxy. Qualitative spot-check of six queries confirmed that top-1 / top-2
results are **topically correct** on 5/6 samples (e.g. Q "Why did Jon start his
dance studio?" → top-1 mentions his studio's investor pitch; Q "What might John's
financial status be?" → top-2 correctly retrieves the "John lost his job at a
mechanical engineering company" fact). This mismatch is why the plan reserves
a real judge stage (Phase 0.3) for ANSWER_* + JUDGE_* env-driven scoring — that
stage is intentionally deferred until the HuggingFace-hosted datasets and the
official-equivalent gateway are online.

Baseline artifacts:

```
runs/dev_baseline_20260806_204940/
  locomo/add_checkpoint.jsonl       # 3 rows
  locomo/search_checkpoint.jsonl    # 60 rows (query + full /search response)
  locomo/proxy.jsonl                # 60 rows (query_id + recall_at_k)
  summary.json                      # aggregate
dev_baseline_20260806_204940.log    # full run log
```

Reproduce:

```bash
python -m evaluation.vividmemory_runner.run full \
    --config evaluation/vividmemory_runner/configs/dev.yaml \
    --run-id my_run_$(date +%Y%m%d_%H%M)
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
| 6   | 6 | README env-var table + progress.md experiment log | — | 0 | 0 | 0 | landed `2f0c690` |
| BL  | — | **defaults baseline measurement** (LoCoMo dev 3×20) | LoCoMo dev | recall@10 = 0.000 (substring proxy; see §6) | deferred | add p50 307s / search p50 0.70s p95 1.01s | measured `dev_baseline_20260806_204940` |

## 8. Per-dataset table

| Dataset | Baseline (proxy recall@10) | Best | Best flags | Label |
|---|---|---|---|---|
| LoCoMo (dev, 3 conv × 20 q) | 0.000 (60/60 retrieved, 0/60 substring-or-Jaccard hits) | — | defaults | [local-dev, deepseek-v4-pro] |
| ScriptMem | not-scored (no adapter yet) | — | — | — |
| BEAM 100K | not-scored (no adapter yet) | — | — | — |
| CL-Bench | not-scored-locally (HF download deferred by user) | — | — | — |
| LongMemEval-S | not-scored-locally (HF download deferred by user) | — | — | — |
| PersonaMem | not-scored-locally (HF download deferred by user) | — | — | — |

Notes:
- LoCoMo proxy = 0.000 does **not** mean retrieval is broken. Qualitative check
  showed topically-correct top-k on 5/6 spot-checked queries. The proxy uses
  literal substring / token-Jaccard≥0.5 vs raw conversational evidence quotes,
  which fact-extraction paraphrases never match.
- Real scoring will require the judge stage (Phase 0.3) once `ANSWER_*` and
  `JUDGE_*` env vars are populated and the deferred datasets are downloaded.

## 9. Failed experiments (kept behind disabled flag or reverted)

_Pending._

## 10. Current best

Flag set:

```
# defaults — no changes yet
```

## 11. Risks

- CL-Bench / LongMemEval / PersonaMem require HF downloads; deferred by the user
  ("先评测vividmemory，deferred后面我再下载" — 2026-08-06). ScriptMem and BEAM local
  data are present but their runner adapters have not been written yet.
- **Substring-based proxy metric under-measures fact-extraction memory.** LoCoMo
  baseline recorded `recall_at_k = 0.000` on 60/60 queries under this proxy while
  qualitative retrieval is topically correct. A judge stage (Phase 0.3) is
  required for a faithful comparison. See §6 for details.
- Cross-encoder rerank adds first-run download; may need Dockerfile pre-fetch step.
- Prompt tuning must not touch benchmark gold answers.
- Ingest latency is dominated by LLM-based fact extraction: 165–388 s per LoCoMo
  conversation (mean 307 s) under `deepseek-v4-pro`. Occasional 502 / transport
  errors from the gateway are absorbed by the runner's exponential-backoff retry
  (Phase 5, `9dc6021`).

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
$ python -m evaluation.vividmemory_runner.run full \
      --config evaluation/vividmemory_runner/configs/dev.yaml \
      --run-id dev_baseline_20260806_204940
# -> runs/dev_baseline_20260806_204940/summary.json
#    { locomo: {num_queries: 60, mean_recall_at_k: 0.000, p50=0.70s, p95=1.01s} }
```
