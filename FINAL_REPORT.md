# VividMemory Contest — Final Report

_Ship date: 2026-08-07. Branch: `perf/contest-memory-optimization`. Baseline commit: `33ba5da`._

## TL;DR

Shipped the "integrated" adapter profile as the Docker default. On the LoCoMo 5-conversation holdout (N=999 questions, deepseek-v4-pro judge), the shipped config scores **35.54% (355/999) vs the pre-ship 31.43% (314/999) — a +4.10 pp lift**. Positive on 4 of 5 conversations, no regressions. N=999 collapses the judge-stochasticity noise band to roughly ±1.3 pp, so the lift is above 3× the noise floor.

Three flags flipped to `true` / `rewrite` / `0.85`. One infrastructure knob raised (`ADAPTER_HTTP_TIMEOUT_SECONDS` 300→1200). No engine-side changes, no schema changes, no new dependencies. Four contract invariants preserved: `/add` idempotency by `request_id`, user isolation via `sha256(user_id)`, `SearchResult` shape, and top-k bounds.

## Configuration flipped

| Env var                              | Old default | New default | Rationale                                                                                    |
| ------------------------------------ | ----------- | ----------- | -------------------------------------------------------------------------------------------- |
| `ADAPTER_RECALL_INCLUDE_OBSERVATIONS`| `false`     | `true`      | Dual retrieval: engine now returns both concept-level facts AND raw observation units.       |
| `ADAPTER_OPTIONS_IN_QUERY_MODE`      | `append`    | `rewrite`   | Strip A./B./C./D. letter prefixes from multi-choice options so they don't pollute recall.    |
| `ADAPTER_NEAR_DEDUP_THRESHOLD`       | `0.0`       | `0.85`      | Token-Jaccard collapse of near-identical concept+observation pairs after dual retrieval.     |
| `ADAPTER_HTTP_TIMEOUT_SECONDS`       | `300`       | `1200`      | Some 600-turn LoCoMo `/add` requests trip the 300s wall on concise extraction.               |

`ADAPTER_EPISODE_PREPEND` stays `false`. `RERANKER_PROVIDER` stays `rrf`. `RETAIN_EXTRACTION_MODE` stays `concise`. `ADAPTER_PER_MESSAGE_RETAIN` stays `false` and remains opt-in.

## Holdout result — LoCoMo 5-conv

Judge: deepseek-v4-pro at temperature 0.0 (some inherent stochasticity remains on borderline CORRECT/WRONG). Answer model: same. Both routed through the deepseek-v4-pro gateway. Question count is the sum across the 5 source conversations.

| Conversation | Baseline correct/total | Integrated correct/total | Δ pp |
| ------------ | ---------------------- | ------------------------ | -----|
| conv-26      | 61 / 199 (30.7%)       | 67 / 199 (33.7%)         | +3.02|
| conv-30      | 22 / 105 (21.0%)       | 22 / 105 (21.0%)         | +0.00|
| conv-41      | 82 / 193 (42.5%)       | 97 / 193 (50.3%)         | +7.77|
| conv-42      | 70 / 260 (26.9%)       | 81 / 260 (31.2%)         | +4.23|
| conv-43      | 79 / 242 (32.6%)       | 88 / 242 (36.4%)         | +3.72|
| **Total**    | **314 / 999 (31.43%)** | **355 / 999 (35.54%)**   |**+4.10**|

Positive on 4 of 5 conversations, flat on 1, negative on 0. Per-conv magnitudes range from +3.02 pp to +7.77 pp. This is a robust lift, not a lucky outlier — the win holds after averaging away single-conv variance.

## Latency

Ingest (5 conversations, `add_concurrency=2`, deepseek-v4-pro internal gateway, concise extraction):

- Total wall-time: 1404 s (~23.4 min)
- Per-conv `/add`: min 135 s (369 msgs), mean 281 s, max 366 s (680 msgs)
- All 5 `/add` calls returned `status=ok`

Search (999 queries, `top_k=10`, `search_concurrency=8`, adapter → engine over Compose network):

- Baseline: p50 = 691 ms, p95 = 975 ms, mean = 712 ms
- Integrated: p50 = 659 ms, p95 = 888 ms, mean = 669 ms

The integrated profile is marginally *faster* at search time even with dual retrieval: near-dedup shrinks the merged candidate set the reranker fuses, more than offsetting the extra observation-side recall.

Answer (baseline, 999 completions, concurrency=8, deepseek-v4-pro internal gateway): ~27 min wall.

Judge (baseline, 999 completions, concurrency=8, deepseek-v4-pro internal gateway): ~13 min wall.

## Source dataset

LoCoMo 5-conv holdout (first 5 conversations of `benchmarks/locomo/data/locomo10.json`):

| sample_id | sessions | messages | questions |
| --------- | -------- | -------- | --------- |
| conv-26   | 19       | 419      | 199       |
| conv-30   | 19       | 369      | 105       |
| conv-41   | 32       | 663      | 193       |
| conv-42   | 29       | 629      | 260       |
| conv-43   | 29       | 680      | 242       |
| **Total** | **128**  | **2760** | **999**   |

## Statistical framing

At N=999 the dev-subset's ±5 pt noise band shrinks to roughly ±1.3 pp (the 3-conv dev subset gave a ±5 pt band across three same-config repeats at N=60; ±5 · √(60/999) ≈ ±1.3). A +4.10 pp effect is about 3× that band, so the lift resolves cleanly on this sample.

The user's decision gate was ≥2–3 pp on the 5-conv holdout, escalating to the full 10-conv holdout only if the result was close, noisy, or contradictory. +4.10 pp with 4 positive and 0 negative per-conv deltas is not close, not noisy, and not contradictory — so we ship without expanding.

## Files touched

Runtime defaults:

- `docker-compose.yml` — flipped `ADAPTER_OPTIONS_IN_QUERY_MODE`, `ADAPTER_RECALL_INCLUDE_OBSERVATIONS`, `ADAPTER_NEAR_DEDUP_THRESHOLD` interpolated defaults; bumped `ADAPTER_HTTP_TIMEOUT_SECONDS` default 300→1200.
- `contest-adapter/app/settings.py` — flipped the same three `Field(default=...)` values; bumped `http_timeout_seconds` default 300.0→1200.0.
- `.env.example` — three shipped-default flags updated with in-file rationale linking here.

Tests:

- `tests/test_settings.py::test_defaults_ship_the_winning_holdout_config` — renamed and updated from the old "preserve current behavior" assertion; now locks in the shipped defaults.
- `tests/test_episode_prepend.py::test_recall_include_observations_can_be_disabled` — renamed and repurposed to verify the explicit-off override still works from the new `true` default.

Docs:

- `README.md` — env-var table refresh, new "Recommended profile" subsection.
- `progress.md` — final experiment table appended.
- `FINAL_REPORT.md` — this document.

Runner infrastructure (opt-in, no default change):

- `evaluation/vividmemory_runner/configs/holdout.yaml` — new 5-conversation holdout config (defaults to the 5-conv gate; comment explains how to expand to the full 10-conv set).

## Rollback / opt-out matrix

Every flipped flag remains a plain env var; setting it to the old value in `.env` before `docker compose up` reverts the behavior with no code change:

- Old `append` options mode: `ADAPTER_OPTIONS_IN_QUERY_MODE=append`
- Old concept-only recall: `ADAPTER_RECALL_INCLUDE_OBSERVATIONS=false`
- Old dedup-off recall: `ADAPTER_NEAR_DEDUP_THRESHOLD=0.0`
- Old 300 s adapter timeout: `ADAPTER_HTTP_TIMEOUT_SECONDS=300`

## Not shipped (kept as opt-in flags)

- **Custom retention extraction** (`RETAIN_EXTRACTION_MODE=custom` with the transitions/dates prompt): still tripped the 1200 s adapter timeout budget on the 663-turn `/add` in one preliminary dry-run; needs session-chunked ingest to be safe, which is scoped out of this ship. Prompt file and activation helper stay committed.
- **`ADAPTER_PER_MESSAGE_RETAIN=true`**: was extrapolated at ≥2.7 h ingest cost per full-LoCoMo run because it fans out to ~1450 individual retain calls on the LLM gateway; not worth the wall-time. Flag stays.
- **Local cross-encoder reranker** (`RERANKER_PROVIDER=local`): the `vividmemory-api-slim` image installs `.[local-onnx]` not `.[local-ml]`, so `sentence-transformers` isn't present and the flag would 500. Fixing that adds ~2 GB to the image; not worth it inside this ship. Flag stays opt-in and documented.
- **`ADAPTER_EPISODE_PREPEND=true`**: prior-session A/B on N=60 showed neutral-to-slightly-negative effect on top of `RECALL_INCLUDE_OBSERVATIONS`. Flag stays opt-in.

## Reproducing the numbers

```bash
docker compose down -v --remove-orphans
docker compose up --build -d --wait

# Baseline (all pre-ship defaults) — flip the three flags back explicitly
ADAPTER_RECALL_INCLUDE_OBSERVATIONS=false \
ADAPTER_OPTIONS_IN_QUERY_MODE=append \
ADAPTER_NEAR_DEDUP_THRESHOLD=0.0 \
  docker compose up -d --force-recreate --wait adapter

python -m evaluation.vividmemory_runner.run ingest \
    --config evaluation/vividmemory_runner/configs/holdout.yaml \
    --run-id holdout_baseline_$(date +%Y%m%d_%H%M)
# runner writes search_checkpoint.jsonl during ingest; then:
python -m evaluation.vividmemory_runner.enrich_locomo \
    --locomo-path benchmarks/locomo/data/locomo10.json \
    --search-jsonl runs/<run_id>/locomo/search_checkpoint.jsonl \
    --output runs/<run_id>/locomo/enriched.jsonl
(set -a; source .env; set +a; \
 python -m evaluation.vividmemory_runner.official_pipeline answer \
    --input  runs/<run_id>/locomo/enriched.jsonl \
    --output runs/<run_id>/locomo/answers.jsonl --concurrency 8 && \
 python -m evaluation.vividmemory_runner.official_pipeline evaluate \
    --input   runs/<run_id>/locomo/enriched.jsonl \
    --answers runs/<run_id>/locomo/answers.jsonl \
    --output  runs/<run_id>/locomo/scores.jsonl --concurrency 8 && \
 python -m evaluation.vividmemory_runner.official_pipeline score \
    --scores runs/<run_id>/locomo/scores.jsonl)

# Integrated (shipped defaults) — reuse the baseline bank via run_experiment.sh
BASELINE_RUN_ID=<run_id> \
ADAPTER_RECALL_INCLUDE_OBSERVATIONS=true \
ADAPTER_OPTIONS_IN_QUERY_MODE=rewrite \
ADAPTER_NEAR_DEDUP_THRESHOLD=0.85 \
ADAPTER_EPISODE_PREPEND=false \
RERANKER_PROVIDER=rrf \
  ./scripts/run_experiment.sh integrated_holdout adapter
```

Answer and judge use whatever `ANSWER_API_*` / `JUDGE_API_*` are set in `.env`. This ship's numbers were produced with `deepseek-v4-pro` (internal gateway) as both answer and judge.

## Verification suite (executed before merge)

```bash
pytest tests/ -v --tb=short          # 43 passed
bash scripts/smoke_test.sh           # health, add→search visibility, isolation, top_k, empty results, idempotent add, temporal update — all green
```
