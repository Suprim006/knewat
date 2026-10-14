# Plexus product image: MCP server (streamable HTTP) and read-only View API. Build context: ./plexus
# docker build -t plexus ./plexus
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PLEXUS_QUERIES_DIR=/app/queries \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    PLEXUS_EMBED_CACHE=/opt/fastembed \
    PLEXUS_EMBED_THREADS=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1

RUN pip install --no-cache-dir uv

WORKDIR /app
# Dependencies first (cached layer), then the project (editable, so queries/ resolves next to src/).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY queries ./queries
RUN uv sync --frozen --no-dev

# Bake the embedding model (int8 bge-small, ~67 MB) so nothing is downloaded at runtime (S2).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')"

RUN useradd --create-home --uid 10001 plexus && chown -R plexus:plexus /app /opt/fastembed
USER plexus
VOLUME ["/opt/fastembed"]

EXPOSE 8765 8080
# Default: the MCP server over streamable HTTP. The View API overrides the command (see docker-compose.yml).
CMD ["plexus-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
