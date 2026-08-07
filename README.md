# VividMemory Contest

Minimal, self-contained Agent Memory Challenge submission.

Provides the official Add/Search HTTP protocol on port **8000**, backed by a private `vividmemory-api-slim` memory engine on port **8888** (Compose-internal only).

## VividMemory implementation summary

This repository is a **finished contest submission** of the VividMemory memory framework for the Agent Memory Challenge Textual Memory track.

**What is implemented**

- A Docker Compose stack that the official evaluator can call over HTTP:
  - `GET /health`, `POST /add`, `POST /search` on port **8000**
- A thin `contest-adapter` that maps the contest protocol onto VividMemory retain/recall
- A private `vividmemory-api-slim` engine with Postgres + pgvector persistence
- Shipped **max-quality** defaults: per-message retain, contest custom extraction, OpenAI `text-embedding-3-large`, local cross-encoder reranker, dual concept+observation recall, option-letter rewrite, near-duplicate collapse, and a 3600s `/add` timeout
- Contract tests + `scripts/smoke_test.sh` for health, visibility, isolation, top-k, and idempotent add

**What the official evaluator should expect**

- Point the evaluator at `http://localhost:8000`
- `/add` stores conversation chunks as memories (LLM fact extraction)
- `/search` returns retrieved memory evidence only — it does **not** call `reflect` and does **not** pick multiple-choice answers
- **No API keys are shipped.** Before `docker compose up`, official testers must fill in their own keys in `.env`:
  - `LLM_API_KEY` — OpenAI (or compatible) key used for **fact extraction** on `/add`
  - `EMBEDDINGS_API_KEY` — a **strong OpenAI embeddings key** (default model: `text-embedding-3-large`) used for vector indexing and recall

**Local-dev note (not an official score):** an earlier integrated search-side profile measured **35.5% vs 31.4%** on a LoCoMo 5-conv holdout (N=999, deepseek-v4-pro judge). The current defaults further enable per-message retain, custom extraction, large embeddings, and a local reranker to prioritize retrieval quality. See `FINAL_REPORT.md`.

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
- An OpenAI (or compatible) **LLM API key** for fact extraction (`LLM_API_KEY`)
- An OpenAI **embeddings API key** for retrieval quality (`EMBEDDINGS_API_KEY`; recommended for official runs)
- Outbound network on first build (Python packages + HuggingFace download of the local cross-encoder weights; ONNX model download only if you fall back to `EMBEDDINGS_PROVIDER=onnx`)
- Several GB of disk for the vividmemory image (`local-ml` includes torch + sentence-transformers)

## Environment variables

Copy and edit:

```bash
cp .env.example .env
```

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Mapped to `VIVIDMEMORY_API_LLM_PROVIDER` |
| `LLM_MODEL` | `gpt-4o-mini` | Mapped to `VIVIDMEMORY_API_LLM_MODEL` |
| `LLM_API_KEY` | _(required — fill in)_ | OpenAI/compatible key for **fact extraction** on `/add` |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Mapped to `VIVIDMEMORY_API_LLM_BASE_URL` |
| `EMBEDDINGS_PROVIDER` | `openai` | Prefer `openai` for official runs; `onnx` only as offline fallback |
| `EMBEDDINGS_MODEL` | `text-embedding-3-large` | Strong OpenAI embedding model |
| `EMBEDDINGS_API_KEY` | _(required for official — fill in)_ | OpenAI embeddings key; if empty, engine falls back to `LLM_API_KEY` |
| `EMBEDDINGS_BASE_URL` | _(optional)_ | OpenAI-compatible embeddings base URL |
| `RERANKER_PROVIDER` | `local` | Local cross-encoder (CPU); set `rrf` to disable |
| `RERANKER_LOCAL_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Used when `RERANKER_PROVIDER=local` |
| `RERANKER_LOCAL_FORCE_CPU` | `true` | Force CPU mode for the local reranker |
| `ADAPTER_INCLUDE_OPTIONS_IN_QUERY` | `true` | Append Search `options` under the original query |
| `ADAPTER_OPTIONS_IN_QUERY_MODE` | `rewrite` | `append` / `none` / `rewrite` (strip option letters, keep option text) |
| `ADAPTER_RECALL_BUDGET` | `high` | Recall token budget passed to the engine |
| `ADAPTER_RECALL_MAX_TOKENS` | `8192` | Recall max tokens returned |
| `ADAPTER_HTTP_TIMEOUT_SECONDS` | `3600` | Adapter → engine HTTP timeout for long per-message `/add` |
| `ADAPTER_PER_MESSAGE_RETAIN` | `true` | Retain each message as its own document |
| `ADAPTER_RETAIN_CONCURRENCY` | `8` | Parallel retain calls per /add |
| `ADAPTER_RECALL_INCLUDE_OBSERVATIONS` | `true` | Include observation-type units in primary recall |
| `ADAPTER_EPISODE_PREPEND` | `false` | Kept off (measured LoCoMo regression) |
| `ADAPTER_EPISODE_PREPEND_COUNT` | `2` | Max prepended episodes when `ADAPTER_EPISODE_PREPEND=true` |
| `ADAPTER_NEAR_DEDUP_THRESHOLD` | `0.85` | Token-Jaccard collapse threshold (0.0 disables) |
| `RETAIN_EXTRACTION_MODE` | `custom` | Contest custom extraction (transitions / dates / quantities) |
| `RETAIN_CUSTOM_INSTRUCTIONS` | _(empty → auto-load)_ | Empty loads `prompts/contest_transitions.txt` via image entrypoint |
| `ANSWER_API_BASE` / `ANSWER_API_KEY` / `ANSWER_MODEL` / `ANSWER_PROVIDER` | _(empty)_ | Answer LLM for the eval runner; env-only |
| `JUDGE_API_BASE` / `JUDGE_API_KEY` / `JUDGE_MODEL` / `JUDGE_VERSION` / `JUDGE_PROVIDER` | _(empty)_ | Judge LLM for the eval runner; env-only |

Default contest stack:

- LLM: OpenAI `gpt-4o-mini` (extraction)
- Embeddings: OpenAI `text-embedding-3-large`
- Reranker: local cross-encoder on CPU (`ms-marco-MiniLM-L-6-v2`)

### Recommended profile (shipped defaults)

Docker defaults prioritize **retrieval quality** over ingest latency:

- `ADAPTER_PER_MESSAGE_RETAIN=true` — finer-grained memories
- `RETAIN_EXTRACTION_MODE=custom` — contest transitions/dates/quantities prompt (auto-loaded)
- `EMBEDDINGS_MODEL=text-embedding-3-large` — strong OpenAI embeddings
- `RERANKER_PROVIDER=local` — CPU cross-encoder rerank
- `ADAPTER_OPTIONS_IN_QUERY_MODE=rewrite` — strip A./B./C./D. option letters
- `ADAPTER_RECALL_INCLUDE_OBSERVATIONS=true` — dual retrieval (concept + observation)
- `ADAPTER_NEAR_DEDUP_THRESHOLD=0.85` — collapse near-duplicate pairs
- `ADAPTER_HTTP_TIMEOUT_SECONDS=3600` — budget for long per-message `/add`
- `ADAPTER_EPISODE_PREPEND=false` — left off after a measured LoCoMo regression

Earlier search-side A/B on LoCoMo 5-conv (N=999, deepseek-v4-pro judge) showed **31.4% → 35.5% (+4.10 pp)** for observations+rewrite+dedup alone. See `FINAL_REPORT.md`.

## One-command start (official / clean clone)

```bash
cp .env.example .env
```

Edit `.env` and **fill in both keys** for the evaluation environment (official testers supply their own):

```env
# 1) Fact extraction during /add — fill in your OpenAI (or compatible) key
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=YOUR_LLM_API_KEY_HERE
LLM_BASE_URL=https://api.openai.com/v1

# 2) Embeddings for indexing + recall — fill in a good OpenAI embeddings key
#    Recommended for official evaluation (do not leave blank if you have OpenAI access).
EMBEDDINGS_PROVIDER=openai
EMBEDDINGS_MODEL=text-embedding-3-large
EMBEDDINGS_API_KEY=YOUR_OPENAI_EMBEDDINGS_API_KEY_HERE
EMBEDDINGS_BASE_URL=https://api.openai.com/v1

# Fallback only: if you truly have no embeddings API, comment out the block above and use:
# EMBEDDINGS_PROVIDER=onnx
```

`LLM_API_KEY` drives **memory extraction**; `EMBEDDINGS_API_KEY` drives **vector retrieval quality**. For official scoring, prefer a real OpenAI embeddings key (`text-embedding-3-large` by default) over the local ONNX fallback. First `docker compose up --build` downloads the local reranker weights into the image (~extra GB).

Then start the stack:

```bash
docker compose up --build -d
# equivalent: docker-compose up --build -d
```

Wait until healthy, then:

- Adapter (official entrypoint): `http://localhost:8000`
- Core API is Compose-internal only (not published on the host)
- Optional smoke check: `bash scripts/smoke_test.sh`

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
# Official testers: fill BOTH keys in .env
#   LLM_API_KEY=YOUR_LLM_API_KEY_HERE                 # fact extraction
#   EMBEDDINGS_API_KEY=YOUR_OPENAI_EMBEDDINGS_API_KEY_HERE  # good OpenAI embedding
# Only if no embeddings API exists: EMBEDDINGS_PROVIDER=onnx
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

The Docker defaults already enable the max-quality profile above. Individual flags remain overridable via `.env` before `docker compose up`.

```bash
# Force concise extraction instead of the contest custom prompt
RETAIN_EXTRACTION_MODE=concise

# Disable local reranker (faster search, usually weaker ranking)
RERANKER_PROVIDER=rrf

# Disable per-message retain (much faster /add, coarser memories)
ADAPTER_PER_MESSAGE_RETAIN=false
```

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

- Retain uses the LLM for fact extraction; `/add` latency grows with per-message retain + custom extraction. Official testers should set `LLM_API_KEY` and expect long ingest times on multi-hundred-turn sessions (timeout budget 3600s).
- Official runs should set `EMBEDDINGS_PROVIDER=openai` plus a strong OpenAI `EMBEDDINGS_API_KEY` (default model `text-embedding-3-large`). Only if no embeddings API is available, fall back to `EMBEDDINGS_PROVIDER=onnx`.
- Search returns memory evidence only; it does not pick an answer from `options`.
- The vividmemory image includes `local-ml` (torch + sentence-transformers) and prefetches the MiniLM cross-encoder; first build needs outbound HuggingFace access and several GB of disk.
- `ADAPTER_EPISODE_PREPEND` stays off by default after a measured LoCoMo regression.

## License

MIT © 2026 959AI994
