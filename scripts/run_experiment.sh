#!/usr/bin/env bash
# Run one A/B experiment against the already-ingested baseline bank.
#
# Usage:
#   ./scripts/run_experiment.sh <exp_name> <service_to_restart>
#
# Expects these env vars to be set by the caller before invocation:
#   - Any ADAPTER_* / RERANKER_* / RETAIN_* overrides for the experiment
#   - BASELINE_RUN_ID (points at the run whose /add already ran)
#
# Reads ANSWER_*/JUDGE_* from .env.

set -euo pipefail

EXP_NAME="${1:?exp name required}"
SERVICE="${2:-adapter}"    # 'adapter' or 'vividmemory'

BASELINE_RUN_ID="${BASELINE_RUN_ID:?BASELINE_RUN_ID must be set}"
BASELINE_DIR="runs/${BASELINE_RUN_ID}/locomo"
EXP_DIR="runs/${BASELINE_RUN_ID}/experiments/${EXP_NAME}"
mkdir -p "$EXP_DIR"

echo "=== Experiment: ${EXP_NAME} (restarting ${SERVICE}) ==="

# Load ANSWER_/JUDGE_ from .env, then let caller's exported flags win.
set -a
source .env
set +a

# Show which experiment flags are active.
echo "--- experiment env overrides ---"
for v in ADAPTER_PER_MESSAGE_RETAIN ADAPTER_RECALL_INCLUDE_OBSERVATIONS \
         ADAPTER_EPISODE_PREPEND ADAPTER_EPISODE_PREPEND_COUNT \
         ADAPTER_OPTIONS_IN_QUERY_MODE ADAPTER_NEAR_DEDUP_THRESHOLD \
         RERANKER_PROVIDER RERANKER_LOCAL_MODEL RERANKER_LOCAL_FORCE_CPU \
         RETAIN_EXTRACTION_MODE; do
  val="${!v:-<unset>}"
  echo "  ${v}=${val}"
done
# RETAIN_CUSTOM_INSTRUCTIONS is long; just print its length.
if [ -n "${RETAIN_CUSTOM_INSTRUCTIONS:-}" ]; then
  echo "  RETAIN_CUSTOM_INSTRUCTIONS length=${#RETAIN_CUSTOM_INSTRUCTIONS}"
fi
echo

# Restart the chosen service so it picks up the new env.
docker compose up -d --force-recreate --wait "${SERVICE}"

# Give it a moment.
sleep 3
curl -sf http://localhost:8000/health > /dev/null || { echo "adapter not healthy"; exit 1; }

# Re-search.
TOP_K="${TOP_K:-10}"
echo "--- re-searching queries (top_k=${TOP_K}) ---"
python -m evaluation.vividmemory_runner.experiment \
    --baseline-search "${BASELINE_DIR}/search_checkpoint.jsonl" \
    --output "${EXP_DIR}/search_checkpoint.jsonl" \
    --top-k "${TOP_K}" \
    --concurrency 8

# Enrich.
python -m evaluation.vividmemory_runner.enrich_locomo \
    --locomo-path benchmarks/locomo/data/locomo10.json \
    --search-jsonl "${EXP_DIR}/search_checkpoint.jsonl" \
    --output "${EXP_DIR}/enriched.jsonl"

# Answer.
echo "--- answer stage ---"
rm -f "${EXP_DIR}/answers.jsonl"
python -m evaluation.vividmemory_runner.official_pipeline answer \
    --input  "${EXP_DIR}/enriched.jsonl" \
    --output "${EXP_DIR}/answers.jsonl" \
    --concurrency 8 2>&1 | tail -3

# Judge.
echo "--- judge stage ---"
python -m evaluation.vividmemory_runner.official_pipeline evaluate \
    --input   "${EXP_DIR}/enriched.jsonl" \
    --answers "${EXP_DIR}/answers.jsonl" \
    --output  "${EXP_DIR}/scores.jsonl" \
    --concurrency 8 2>&1 | tail -3

# Score.
echo
echo "=== ${EXP_NAME} score ==="
python -m evaluation.vividmemory_runner.official_pipeline score \
    --scores "${EXP_DIR}/scores.jsonl" | tee "${EXP_DIR}/score.json"
