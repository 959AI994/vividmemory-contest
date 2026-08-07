#!/usr/bin/env bash
# Enable the engine's local cross-encoder reranker (Phase 4A).
#
# Usage:
#     source scripts/enable_local_reranker.sh
#     docker compose up -d --wait
#
# Notes:
#   - First activation triggers a one-time download of the reranker weights
#     (cross-encoder/ms-marco-MiniLM-L-6-v2, ~90 MB) inside the vividmemory
#     container. Subsequent starts reuse the cached weights.
#   - RERANKER_LOCAL_FORCE_CPU stays true so this runs on any Docker host,
#     including hosts without a GPU.

set -euo pipefail

export RERANKER_PROVIDER="local"
export RERANKER_LOCAL_FORCE_CPU="${RERANKER_LOCAL_FORCE_CPU:-true}"
export RERANKER_LOCAL_MODEL="${RERANKER_LOCAL_MODEL:-cross-encoder/ms-marco-MiniLM-L-6-v2}"

echo "RERANKER_PROVIDER=$RERANKER_PROVIDER"
echo "RERANKER_LOCAL_FORCE_CPU=$RERANKER_LOCAL_FORCE_CPU"
echo "RERANKER_LOCAL_MODEL=$RERANKER_LOCAL_MODEL"
