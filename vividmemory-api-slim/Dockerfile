FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Non-root user + pg0 data directory
RUN useradd -m -u 1000 vividmemory \
    && mkdir -p /home/vividmemory/.pg0 \
    && chown -R vividmemory:vividmemory /home/vividmemory /app

COPY --chown=vividmemory:vividmemory pyproject.toml README.md ./
COPY --chown=vividmemory:vividmemory vividmemory_api ./vividmemory_api

# Contest image: embedded Postgres + OpenAI embeddings by default.
# local-onnx is also installed so EMBEDDINGS_PROVIDER=onnx works without torch.
# Reranker defaults to RRF passthrough (no neural local model required).
USER vividmemory
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV HOME=/home/vividmemory
ENV PATH="/app/.venv/bin:$PATH"
ENV HF_HUB_DOWNLOAD_TIMEOUT=600

RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python -e ".[embedded-db,local-onnx]" \
    && /app/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

ENV PYTHONUNBUFFERED=1
ENV TOKENIZERS_PARALLELISM=false
ENV VIVIDMEMORY_API_HOST=0.0.0.0
ENV VIVIDMEMORY_API_PORT=8888
ENV VIVIDMEMORY_API_DATABASE_URL=pg0://contest
ENV VIVIDMEMORY_API_EMBEDDINGS_PROVIDER=openai
ENV VIVIDMEMORY_API_EMBEDDINGS_OPENAI_MODEL=text-embedding-3-small
ENV VIVIDMEMORY_API_RERANKER_PROVIDER=rrf

EXPOSE 8888

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=30 \
  CMD curl -fsS http://127.0.0.1:8888/health || exit 1

CMD ["vividmemory-api"]
