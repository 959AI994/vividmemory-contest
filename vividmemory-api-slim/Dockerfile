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
COPY --chown=vividmemory:vividmemory prompts ./prompts
COPY --chown=vividmemory:vividmemory docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Contest image: local-onnx for optional offline embeddings; local-ml for
# the default CPU cross-encoder reranker (sentence-transformers + torch).
USER vividmemory
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
ENV HOME=/home/vividmemory
ENV PATH="/app/.venv/bin:$PATH"
ENV HF_HUB_DOWNLOAD_TIMEOUT=600
ENV HF_HOME=/home/vividmemory/.cache/huggingface

RUN uv venv /app/.venv \
    && uv pip install --python /app/.venv/bin/python -e ".[local-onnx,local-ml]" \
    && /app/.venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')" \
    && /app/.venv/bin/python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

ENV PYTHONUNBUFFERED=1
ENV TOKENIZERS_PARALLELISM=false
ENV VIVIDMEMORY_API_HOST=0.0.0.0
ENV VIVIDMEMORY_API_PORT=8888
ENV VIVIDMEMORY_API_EMBEDDINGS_PROVIDER=openai
ENV VIVIDMEMORY_API_EMBEDDINGS_OPENAI_MODEL=text-embedding-3-large
ENV VIVIDMEMORY_API_RERANKER_PROVIDER=local
ENV VIVIDMEMORY_API_RERANKER_LOCAL_FORCE_CPU=true
ENV VIVIDMEMORY_API_RERANKER_LOCAL_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
ENV VIVIDMEMORY_API_RETAIN_EXTRACTION_MODE=custom
ENV VIVIDMEMORY_API_MCP_ENABLED=false
ENV CONTEST_EXTRACTION_PROMPT_FILE=/app/prompts/contest_transitions.txt

EXPOSE 8888

HEALTHCHECK --interval=10s --timeout=5s --start-period=300s --retries=30 \
  CMD curl -fsS http://127.0.0.1:8888/health || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["vividmemory-api"]
