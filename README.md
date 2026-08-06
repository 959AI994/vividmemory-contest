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
  embedded PostgreSQL (pg0)
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
| `RERANKER_PROVIDER` | `rrf` | RRF passthrough (no local cross-encoder) |
| `ADAPTER_INCLUDE_OPTIONS_IN_QUERY` | `true` | Append Search `options` under the original query |

Default contest stack:

- LLM: OpenAI `gpt-4o-mini`
- Embeddings: OpenAI `text-embedding-3-small`
- Reranker: `rrf` (no neural reranker)

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

## Persistence

Named Docker volume: `vividmemory_pg0`  
Mounted at: `/home/vividmemory/.pg0` inside the `vividmemory` container.

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
