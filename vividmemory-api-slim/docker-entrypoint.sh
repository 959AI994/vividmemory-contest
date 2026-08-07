#!/usr/bin/env bash
# Contest image entrypoint: bake max-quality extraction defaults when unset.
set -euo pipefail

PROMPT_FILE="${CONTEST_EXTRACTION_PROMPT_FILE:-/app/prompts/contest_transitions.txt}"

# Default to contest custom extraction when the caller did not override.
if [[ -z "${VIVIDMEMORY_API_RETAIN_EXTRACTION_MODE:-}" ]]; then
  export VIVIDMEMORY_API_RETAIN_EXTRACTION_MODE=custom
fi

# When custom mode is active and instructions are empty, load the shipped prompt.
if [[ "${VIVIDMEMORY_API_RETAIN_EXTRACTION_MODE}" == "custom" \
   && -z "${VIVIDMEMORY_API_RETAIN_CUSTOM_INSTRUCTIONS:-}" \
   && -f "${PROMPT_FILE}" ]]; then
  export VIVIDMEMORY_API_RETAIN_CUSTOM_INSTRUCTIONS="$(cat "${PROMPT_FILE}")"
fi

exec "$@"
