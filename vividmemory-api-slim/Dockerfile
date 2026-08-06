FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

RUN useradd -m -u 1000 vividmemory \
    && chown -R vividmemory:vividmemory /app

COPY --chown=vividmemory:vividmemory pyproject.toml README.md ./
COPY --chown=vividmemory:vividmemory vividmemory_api ./vividmemory_api

# Contest image talks to Compose Postgres. local-onnx is optional for EMBEDDINGS_PROVIDER=onnx.
USER vividmemory
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV HOME=/home/vividmemory
ENV PATH="/app/.venv/bin:$PATH"
ENV HF_HUB_DOWNLOAD_TIMEOUT=600

RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python -e ".[local-onnx]" \
    && /app/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

ENV PYTHONUNBUFFERED=1
ENV TOKENIZERS_PARALLELISM=false
ENV VIVIDMEMORY_API_HOST=0.0.0.0
ENV VIVIDMEMORY_API_PORT=8888
ENV VIVIDMEMORY_API_EMBEDDINGS_PROVIDER=openai
ENV VIVIDMEMORY_API_EMBEDDINGS_OPENAI_MODEL=text-embedding-3-small
ENV VIVIDMEMORY_API_RERANKER_PROVIDER=rrf
ENV VIVIDMEMORY_API_MCP_ENABLED=false

EXPOSE 8888

HEALTHCHECK --interval=10s --timeout=5s --start-period=180s --retries=30 \
  CMD curl -fsS http://127.0.0.1:8888/health || exit 1

CMD ["vividmemory-api"]
