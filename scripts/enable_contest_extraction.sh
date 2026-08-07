#!/usr/bin/env bash
# Enable the contest custom extraction prompt (Phase 2).
#
# Usage:
#     source scripts/enable_contest_extraction.sh
#     docker compose up -d
#
# Reverts to default 'concise' mode by opening a fresh shell.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROMPT_FILE="$SCRIPT_DIR/../vividmemory-api-slim/prompts/contest_transitions.txt"

if [[ ! -f "$PROMPT_FILE" ]]; then
    echo "prompt file not found: $PROMPT_FILE" >&2
    return 1 2>/dev/null || exit 1
fi

export RETAIN_EXTRACTION_MODE="custom"
export RETAIN_CUSTOM_INSTRUCTIONS="$(cat "$PROMPT_FILE")"

echo "RETAIN_EXTRACTION_MODE=custom"
echo "RETAIN_CUSTOM_INSTRUCTIONS length: ${#RETAIN_CUSTOM_INSTRUCTIONS} chars"
