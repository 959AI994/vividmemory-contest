# VividMemory Contest Benchmark Runner (Skeleton)

Minimal, offline-first benchmark scaffolding. This is the Phase 0.2 skeleton
and covers **ingest → search → proxy** only. Answer/judge stages are not
implemented here; the surrounding plan (`progress.md`, Phase 0.3) documents
those as `ANSWER_*` / `JUDGE_*` env-only configuration for a later phase.

## Layout

```
evaluation/vividmemory_runner/
  __init__.py
  run.py            CLI entrypoint (python -m evaluation.vividmemory_runner.run ...)
  config.py         RunConfig + YAML loader
  client.py         async httpx client for /add /search /health
  checkpointing.py  append-only JSONL + resume helpers
  adapters/         per-benchmark dataset adapters (currently: locomo)
  proxy/            cheap proxy metrics (recall@k substring)
  configs/          dev.yaml
```

Adapters for BEAM, ScriptMem, CL-Bench, LongMemEval, PersonaMem are
placeholders — extend `adapters/` and register the loader in
`run._LOADERS` to add support.

## Usage

Prerequisite: contest stack up (`docker compose up -d --wait`).

```bash
# Sanity
python -m evaluation.vividmemory_runner.run health \
    --config evaluation/vividmemory_runner/configs/dev.yaml

# End-to-end
python -m evaluation.vividmemory_runner.run full \
    --config evaluation/vividmemory_runner/configs/dev.yaml \
    --run-id my_run_001

# Or step-by-step (resumable)
python -m evaluation.vividmemory_runner.run ingest --config ... --run-id my_run_001
python -m evaluation.vividmemory_runner.run search --config ... --run-id my_run_001
python -m evaluation.vividmemory_runner.run proxy  --config ... --run-id my_run_001
```

Outputs land under `runs/{run_id}/{dataset}/`:
- `add_checkpoint.jsonl` — one row per ingested conversation
- `search_checkpoint.jsonl` — one row per query + full /search response
- `proxy.jsonl` — per-query recall@k
- `runs/{run_id}/summary.json` — aggregated per-dataset metrics

## Naming (avoids cross-run contamination)

- `user_id = eval:{run_id}:{dataset}:{conv_id}:{speaker_key}`
- `session_id = eval:{run_id}:{dataset}:{conv_id}:s{session_index}`
- `request_id = eval:{run_id}:{dataset}:{conv_id}:{speaker_key}:0`

## Not implemented in the skeleton

- Answer-model invocation (requires `ANSWER_API_*` env vars — see plan §Phase 0.3).
- Judge-model invocation (requires `JUDGE_API_*` env vars).
- Adapters for BEAM, ScriptMem, CL-Bench, LongMemEval, PersonaMem.
- Adaptive concurrency reduction on 5xx bursts (Phase 5).
- Aggregator that merges across datasets into a leaderboard-style report.

These are deliberate defer-points; the skeleton is intentionally small so it
can be extended in follow-up phases without invalidating checkpoints.
