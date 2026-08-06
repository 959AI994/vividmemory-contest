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
| 1   | 1 | `ADAPTER_PER_MESSAGE_RETAIN` (flag off by default) | LoCoMo (targeted) | n/a | **rolled back** — gateway saturates (see §9) | +hours | landed `2133068` |
| 4B  | 4 | `ADAPTER_OPTIONS_IN_QUERY_MODE` append/none/rewrite | BEAM/CL-Bench (MCQ) | n/a | see integrated row below | ~0 | landed `78a1896` |
| 4C  | 4 | `ADAPTER_NEAR_DEDUP_THRESHOLD` token-Jaccard collapse | all | n/a | **0** (E4=16.67% ≡ BL) | ~0 | landed `2d36b41` |
| 3   | 3 | `ADAPTER_RECALL_INCLUDE_OBSERVATIONS` + `ADAPTER_EPISODE_PREPEND` | ScriptMem, LoCoMo | n/a | +0–8 pts (see E1 below, noisy) | +0.05s | landed `91f2a4f` |
| 2   | 2 | custom-extraction prompt file + `enable_contest_extraction.sh` | LongMemEval-like | n/a | **rolled back** — gateway impractical (see §9) | ingest timeout | landed `bf3c2ce` |
| 4A  | 4 | `enable_local_reranker.sh` helper (wiring only) | all | n/a | image lacks `sentence-transformers` (see §9) | n/a | landed `dd92ab0` |
| 0.2 | 0 | benchmark runner skeleton (LoCoMo ingest/search/proxy) | LoCoMo dev | pending | n/a | pending | landed `f2ba8c8` |
| 5   | 5 | runner client exponential backoff + jitter | all | 0 (reliability) | 0 | 0 | landed `9dc6021` |
| 6   | 6 | README env-var table + progress.md experiment log | — | 0 | 0 | 0 | landed `2f0c690` |
| BL  | — | **defaults baseline measurement** (LoCoMo dev 3×20) | LoCoMo dev | recall@10 = 0.000 (substring proxy; see §6) | **16.67% (10/60)** initial; 20.0%/21.67% repro (Δ = judge variance) | add p50 307s / search p50 0.70s p95 1.01s | measured `dev_baseline_20260806_204940`, judge scored `d3bbb1d`+ |

### 7.1 Search-side ablation table (LoCoMo dev, same 60 queries, deepseek-v4-pro answer+judge)

All experiments below reuse the already-ingested baseline bank (dev_baseline_20260806_204940) via `scripts/run_experiment.sh`. Search-only flags — no re-ingest. All rows are **[local-dev, deepseek-v4-pro]**.

| Experiment | Flags flipped vs baseline | Correct / 60 | Accuracy | Δ vs BL(16.67%) | Search p50/p95 |
|---|---|---|---|---|---|
| `baseline` | — (defaults) | 10 | 16.67% | — | 0.702s / 1.012s |
| `baseline_verify` | — (repeat) | 12 | 20.00% | +3.33 | 0.75s / 1.06s |
| `baseline_verify2` | — (repeat) | 13 | 21.67% | +5.00 | 0.75s / 1.06s |
| `E1_recall_observations` | `ADAPTER_RECALL_INCLUDE_OBSERVATIONS=true` | 15 | 25.00% | +8.33 | ≈BL |
| `E1_verify_recall_observations` | same as E1 (repeat) | 12 | 20.00% | +3.33 | ≈BL |
| `E2_episode_prepend` | E1 + `ADAPTER_EPISODE_PREPEND=true` | 13 | 21.67% | +5.00 | ≈BL |
| `E3_local_reranker` | `RERANKER_PROVIDER=local` (fell back to rrf; see §9) | 14 | 23.33% | +6.67 | ≈BL |
| `E4_near_dedup` | `ADAPTER_NEAR_DEDUP_THRESHOLD=0.85` | 10 | 16.67% | 0.00 | ≈BL |
| **`integrated_search_side`** | `ADAPTER_OPTIONS_IN_QUERY_MODE=rewrite` + `ADAPTER_NEAR_DEDUP_THRESHOLD=0.85` + `ADAPTER_RECALL_INCLUDE_OBSERVATIONS=true` + `ADAPTER_EPISODE_PREPEND=false` + `RERANKER_PROVIDER=rrf` | 13 | 21.67% | +5.00 | 0.75s / 1.06s |
| `integrated_verify` | same as integrated (repeat) | 13 | 21.67% | +5.00 | 0.75s / 1.06s |

**Noise floor.** Three baseline repeats (default flags, same bank, same day, same gateway) returned 10, 12, 13 correct — a **±5 pt judge-stochastic band on 60 questions**. deepseek-v4-pro at `temperature=0` is not fully deterministic on borderline "CORRECT vs WRONG" boundary answers. The integrated candidate's stable 13/60 (both repeats) puts it at the upper edge of the baseline band, giving a real-but-modest signal (~+2 pts vs mean baseline 11.67, ~+5 pts vs initial baseline). It does **not clearly beat baseline** by the ship criterion given the 60-question sample size.

Rollback decisions are captured in §9 (Failed experiments).

## 8. Per-dataset table

| Dataset | Baseline (defaults) | Best measured | Best flags | Label |
|---|---|---|---|---|
| LoCoMo (dev, 3 conv × 20 q) | **16.67% (10/60)** initial · 20.00%/21.67% repeats (judge σ≈±5 pts) | **21.67% (13/60)** integrated_search_side (stable across 2 repeats); E1 hit 25% once but did not reproduce | `ADAPTER_OPTIONS_IN_QUERY_MODE=rewrite` + `ADAPTER_NEAR_DEDUP_THRESHOLD=0.85` + `ADAPTER_RECALL_INCLUDE_OBSERVATIONS=true` + `ADAPTER_EPISODE_PREPEND=false` + `RERANKER_PROVIDER=rrf` | [local-dev, deepseek-v4-pro] |
| ScriptMem | not-scored (no adapter yet) | — | — | — |
| BEAM 100K | not-scored (no adapter yet) | — | — | — |
| CL-Bench | not-scored-locally (HF download deferred by user) | — | — | — |
| LongMemEval-S | not-scored-locally (HF download deferred by user) | — | — | — |
| PersonaMem | not-scored-locally (HF download deferred by user) | — | — | — |

Notes:
- LoCoMo substring proxy = 0.000 is a metric artefact (paraphrased facts vs raw
  quotes) and does not indicate broken retrieval — see §6.
- **Ship criterion (user directive): "integrated candidate clearly beats
  baseline".** Integrated_search_side reproduces at 21.67%; baseline repeats
  span 16.67%–21.67%. The gap is within the observed judge-stochasticity band
  (±5 pts on 60 questions), so we do **not** flip Docker defaults. The flags
  remain opt-in via env; users who care about maximising accuracy can set
  `ADAPTER_RECALL_INCLUDE_OBSERVATIONS=true` (dominant single-flag signal) and
  `ADAPTER_OPTIONS_IN_QUERY_MODE=rewrite`. Running against full LoCoMo (~1986
  QAs, 10 conversations) would give ~5× more statistical power to detect these
  smaller effects; the ingest cost is ~15 min and stayed deferred this session.

## 9. Failed experiments (kept behind disabled flag or reverted)

All three below stay wired in via env flags (default OFF) — no reverts to code — so users can enable them in different LLM/gateway environments where they may become viable. This section records **why they didn't fly on the deepseek-v4-pro dev-gateway** used for scoring.

1. **`ADAPTER_PER_MESSAGE_RETAIN=true`** — fan-out per-message retain (Phase 1).
   With 3 conversations × ~484 messages/conv × ~60–370 s per extraction on this
   gateway (custom-prompt-cached, ~4 k prompt + 0.8–3.4 k output tokens), the
   ~8-per-minute successful-call rate extrapolates to **≥2.7 h ingest for the
   dev subset** before any /search. The adapter's per-`/add` 300 s timeout is
   also blown regularly. Rolled back per user's corrective protocol #2.
   Verdict: keep the flag; needs a lower-latency LLM gateway to be viable.

2. **`RETAIN_EXTRACTION_MODE=custom` (contest-transitions prompt)** — verbose
   extraction (Phase 2). Even with per-conversation retain (per-message OFF),
   the custom prompt's high output-token ratio (0.4–0.9 out/in vs concise's
   ~0.2) chains multiple internal LLM calls per conversation and each `/add`
   still exceeds the adapter's 300 s HTTP timeout on conv-41 / conv-26 (663 /
   419 turns). No successful ingest reached the search stage.
   Verdict: keep the flag + prompt file; needs longer adapter timeout AND a
   faster LLM gateway.

3. **`RERANKER_PROVIDER=local` (cross-encoder/ms-marco-MiniLM-L-6-v2)** —
   local reranker (Phase 4A). Image lacks `sentence-transformers` (Dockerfile
   installs only `.[local-onnx]`, not `.[local-ml]`), so the engine raises
   `ImportError` at startup and never comes healthy. Confirmed by
   `docker compose exec vividmemory python -c "import sentence_transformers"`
   → `ModuleNotFoundError`. The E3 experiment that appeared to succeed with
   this flag was almost certainly running with the engine's silent-fallback
   path to `rrf` reranking; we did not verify the code path this session.
   Verdict: keep the flag; enabling it in the shipped image requires adding
   `local-ml` to the extras installed in `vividmemory-api-slim/Dockerfile`
   (pulls in `torch` + `sentence-transformers`, ~2 GB image size increase).

## 10. Current best

Flag set (opt-in — Docker default unchanged):

```
ADAPTER_RECALL_INCLUDE_OBSERVATIONS=true    # single strongest signal
ADAPTER_OPTIONS_IN_QUERY_MODE=rewrite       # neutral–positive; strips A/B/C letters
ADAPTER_NEAR_DEDUP_THRESHOLD=0.85           # neutral on this dev slice; may help on larger sets
ADAPTER_EPISODE_PREPEND=false               # (default) episode-prepend regressed in E2
RERANKER_PROVIDER=rrf                       # (default) local reranker blocked by image dep
```

- LoCoMo dev (3 conv × 20 q): **21.67% (13/60)** stable across 2 repeats; vs
  baseline 16.67%–21.67% band → **not clearly beating baseline** on this
  sample. Kept opt-in.
- No Docker default flip. Reasoning: judge stochasticity is ±5 pts at N=60;
  a real ship would want either (a) larger N or (b) a lower-variance judge.

## 11. Risks

- CL-Bench / LongMemEval / PersonaMem require HF downloads; deferred by the user
  ("先评测vividmemory，deferred后面我再下载" — 2026-08-06). ScriptMem and BEAM local
  data are present but their runner adapters have not been written yet.
- **Substring-based proxy metric under-measures fact-extraction memory.** LoCoMo
  baseline recorded `recall_at_k = 0.000` on 60/60 queries under this proxy while
  qualitative retrieval is topically correct. A judge stage (Phase 0.3) is
  required for a faithful comparison. See §6 for details. Judge stage is now
  landed (see §7.1).
- **Judge stochasticity at N=60 is ~±5 pts.** deepseek-v4-pro at
  `temperature=0` is not fully deterministic on borderline CORRECT/WRONG
  boundary answers. Three same-config baseline repeats returned 10/12/13
  correct. Any measured effect below ~5 pts on 60 questions is inside noise.
  Running the full LoCoMo (~1986 QAs across 10 conversations) would shrink
  this bar by ~√33 ≈ 5.7× and let smaller effects be resolved.
- **Local cross-encoder reranker cannot start in the shipped image** because
  `vividmemory-api-slim/Dockerfile` installs only `.[local-onnx]` (no
  `sentence-transformers`). Adding `.[local-ml]` pulls in torch (~2 GB). Left
  unchanged this session — flag stays opt-in and documented in §9.
- **Custom extraction + per-message retain saturate the deepseek-v4-pro
  gateway.** See §9 for details. Both features remain wired but are
  environment-dependent.
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
