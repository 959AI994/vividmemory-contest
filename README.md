# VividMemory Contest

Minimal, self-contained Agent Memory Challenge submission.

Provides the official Add/Search HTTP protocol on port **8000**, backed by a private `vividmemory-api-slim` memory engine on port **8888** (Compose-internal only).

## Architecture

```text
Official Evaluator
        |
        v
contest-adapter :8000
  GET  /health
  POST /add
  POST /search
        |
        v
vividmemory-api-slim :8888
  POST /v1/default/banks/{bank_id}/memories          (retain)
  POST /v1/default/banks/{bank_id}/memories/recall   (recall)
        |
        v
PostgreSQL + pgvector (Compose service `db`)
```

The adapter is a thin protocol layer. It does **not** call `reflect` and does **not** choose multiple-choice answers. Search only returns retrieved memory evidence.

## Directory layout

```text
vividmemory-contest/
├── vividmemory-api-slim/   # Core memory engine (FastAPI)
├── contest-adapter/        # Contest Add/Search adapter
├── tests/                  # Offline contract tests
├── scripts/smoke_test.sh   # Live end-to-end smoke test
├── docker-compose.yml
├── .env.example
└── README.md
```

## Requirements

- Docker Engine + Docker Compose v2
- An LLM API key (default: OpenAI)
- Outbound network on first build (Python package download; ONNX model download if `EMBEDDINGS_PROVIDER=onnx`)

## Environment variables

Copy and edit:

```bash
cp .env.example .env
```

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Mapped to `VIVIDMEMORY_API_LLM_PROVIDER` |
| `LLM_MODEL` | `gpt-4o-mini` | Mapped to `VIVIDMEMORY_API_LLM_MODEL` |
| `LLM_API_KEY` | _(required)_ | Mapped to `VIVIDMEMORY_API_LLM_API_KEY` |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Mapped to `VIVIDMEMORY_API_LLM_BASE_URL` |
| `EMBEDDINGS_PROVIDER` | `openai` | `openai` or `onnx` |
| `EMBEDDINGS_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `EMBEDDINGS_API_KEY` | _(optional)_ | Falls back to `LLM_API_KEY` inside the engine |
| `EMBEDDINGS_BASE_URL` | _(optional)_ | OpenAI-compatible embeddings base URL |
| `RERANKER_PROVIDER` | `rrf` | `rrf` passthrough or `local` cross-encoder |
| `RERANKER_LOCAL_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Only used when `RERANKER_PROVIDER=local` |
| `RERANKER_LOCAL_FORCE_CPU` | `true` | Force CPU mode for the local reranker |
| `ADAPTER_INCLUDE_OPTIONS_IN_QUERY` | `true` | Append Search `options` under the original query |
| `ADAPTER_OPTIONS_IN_QUERY_MODE` | `rewrite` | `append` / `none` / `rewrite` (strip option letters, keep option text) |
| `ADAPTER_RECALL_BUDGET` | `high` | Recall token budget passed to the engine |
| `ADAPTER_RECALL_MAX_TOKENS` | `8192` | Recall max tokens returned |
| `ADAPTER_HTTP_TIMEOUT_SECONDS` | `1200` | Adapter → engine HTTP timeout; long enough for the slowest 600-turn `/add` |
| `ADAPTER_PER_MESSAGE_RETAIN` | `false` | Retain each message as its own document |
| `ADAPTER_RETAIN_CONCURRENCY` | `4` | Parallel retain calls per /add |
| `ADAPTER_RECALL_INCLUDE_OBSERVATIONS` | `true` | Include observation-type units in primary recall |
| `ADAPTER_EPISODE_PREPEND` | `false` | Second recall for raw-episode units, prepended before dedup |
| `ADAPTER_EPISODE_PREPEND_COUNT` | `2` | Max prepended episodes when `ADAPTER_EPISODE_PREPEND=true` |
| `ADAPTER_NEAR_DEDUP_THRESHOLD` | `0.85` | Token-Jaccard collapse threshold (0.0 disables) |
| `RETAIN_EXTRACTION_MODE` | `concise` | `concise` / `verbose` / `custom` extraction |
| `RETAIN_CUSTOM_INSTRUCTIONS` | _(empty)_ | Only used when mode=`custom`; see `scripts/enable_contest_extraction.sh` |
| `ANSWER_API_BASE` / `ANSWER_API_KEY` / `ANSWER_MODEL` / `ANSWER_PROVIDER` | _(empty)_ | Answer LLM for the eval runner; env-only |
| `JUDGE_API_BASE` / `JUDGE_API_KEY` / `JUDGE_MODEL` / `JUDGE_VERSION` / `JUDGE_PROVIDER` | _(empty)_ | Judge LLM for the eval runner; env-only |

Default contest stack:

- LLM: OpenAI `gpt-4o-mini`
- Embeddings: OpenAI `text-embedding-3-small`
- Reranker: `rrf` (no neural reranker)

### Recommended profile (shipped defaults)

The Docker defaults are already the LoCoMo-tuned "integrated" profile that shipped on 2026-08-07:

- `ADAPTER_OPTIONS_IN_QUERY_MODE=rewrite` — strip A./B./C./D. option letters so they don't pollute recall
- `ADAPTER_RECALL_INCLUDE_OBSERVATIONS=true` — dual retrieval (concept + observation)
- `ADAPTER_NEAR_DEDUP_THRESHOLD=0.85` — collapse near-duplicate concept/observation pairs
- `ADAPTER_HTTP_TIMEOUT_SECONDS=1200` — accommodates the slowest 600-turn `/add`

Measured lift over the pre-2026-08-07 defaults on the LoCoMo 5-conv holdout (N=999 questions, deepseek-v4-pro judge): **31.4% → 35.5% (+4.10 pp)**. Positive on 4 of 5 conversations, zero regressions. See `FINAL_REPORT.md`. To revert to the pre-ship profile, set the three adapter flags above back to `append` / `false` / `0.0` in `.env` before `docker compose up`.

## One-command start

```bash
cp .env.example .env
# put your key into LLM_API_KEY

docker compose up --build -d
# equivalent: docker-compose up --build -d
```

Wait until healthy, then:

- Adapter: `http://localhost:8000`
- Core API is not published on the host (Compose internal only)

## Stop / clean

```bash
# stop containers
docker compose down

# stop and delete persisted memory DB volume
docker compose down -v
```

## API examples

### Health

```bash
curl -s http://localhost:8000/health
```

### Add

```bash
curl -s http://localhost:8000/add \
  -H 'Content-Type: application/json' \
  -d '{
    "request_id": "eval:run_demo:chunk-0",
    "messages": [
      {
        "role": "user",
        "timestamp": 1704067200000,
        "content": "Alice moved from Boston to Seattle in July 2026."
      }
    ],
    "user_id": "eval:run_demo:user-0",
    "session_id": "eval:run_demo:session-0"
  }'
```

### Search

```bash
curl -s http://localhost:8000/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "Where does Alice currently live?",
    "options": ["A. Boston", "B. Seattle"],
    "user_id": "eval:run_demo:user-0",
    "top_k": 10
  }'
```

Expected shape:

```json
{
  "data": [
    {
      "id": "...",
      "content": "...",
      "score": 0.91,
      "created_at": "2026-07-20T00:00:00Z"
    }
  ]
}
```

`score` / `created_at` are optional. Empty recall returns `{"data":[]}`.

## Fresh clone runbook

```bash
git clone git@github.com:959AI994/vividmemory-contest.git
cd vividmemory-contest
cp .env.example .env
# edit LLM_API_KEY
docker compose up --build -d
bash scripts/smoke_test.sh
```

## Smoke test

```bash
bash scripts/smoke_test.sh
```

Covers health, add→search visibility, user isolation, `top_k`, empty results, idempotent add, and temporal update queries.

Offline unit tests:

```bash
pip install pytest pydantic pydantic-settings httpx fastapi
pytest -q tests/
```

## Optional feature toggles

The Docker defaults ship the winning "integrated" profile (see the **Recommended profile** subsection above). Each individual flag is still documented in `.env.example` and wired in `docker-compose.yml`, so you can flip any one back to its pre-ship value by setting it in `.env` before `docker compose up`.

Two helper scripts export the required env vars into the current shell:

```bash
# Enable the contest custom extraction prompt (Phase 2).
source scripts/enable_contest_extraction.sh
docker compose up -d --wait

# Enable the engine's local cross-encoder reranker (Phase 4A).
source scripts/enable_local_reranker.sh
docker compose up -d --wait
```

The other adapter flags (`ADAPTER_PER_MESSAGE_RETAIN`, `ADAPTER_EPISODE_PREPEND`,
`ADAPTER_RECALL_INCLUDE_OBSERVATIONS`, `ADAPTER_OPTIONS_IN_QUERY_MODE`,
`ADAPTER_NEAR_DEDUP_THRESHOLD`) can be flipped by setting them in `.env`
before `docker compose up -d`.

## Benchmark runner (dev only)

A minimal offline runner lives under `evaluation/vividmemory_runner/`. It
covers **ingest → search → proxy** for LoCoMo (10-conversation dataset). See
`evaluation/vividmemory_runner/README.md` for details.

```bash
python -m evaluation.vividmemory_runner.run full \
    --config evaluation/vividmemory_runner/configs/dev.yaml \
    --run-id dev_$(date +%Y%m%d_%H%M)
```

Answer/judge stages require `ANSWER_API_*` / `JUDGE_API_*` env vars and are
deliberately not implemented in the skeleton (see plan Phase 0.3).

## Persistence

Named Docker volume: `vividmemory_pgdata`  
Mounted at: `/var/lib/postgresql/data` in the `db` container (`pgvector/pgvector:pg16`).

Reset all evaluation data:

```bash
docker compose down -v
```

## Protocol mapping

| Contest | VividMemory |
|---|---|
| `user_id` | `bank_id = "contest-" + sha256(user_id)` |
| `POST /add` | sync `POST /v1/default/banks/{bank_id}/memories` with one conversation document, `document_id=request_id`, `async=false`, `update_mode=replace` |
| `POST /search` | `POST /v1/default/banks/{bank_id}/memories/recall` only (`reflect` never called) |

## Known limitations

- Retain uses the LLM for fact extraction; `/add` latency depends on the provider.
- Default embeddings require an OpenAI-compatible embeddings endpoint. If your LLM gateway has no embeddings API, set `EMBEDDINGS_PROVIDER=onnx`.
- Search returns memory evidence only; it does not pick an answer from `options`.
- First `onnx` run downloads the ONNX embedding model into the container.

## License

MIT © 2026 959AI994
