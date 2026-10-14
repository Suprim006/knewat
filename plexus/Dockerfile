# Plexus product image: MCP server (streamable HTTP) and read-only View API. Build context: ./plexus
# docker build -t plexus ./plexus
# Base image pinned by digest (python:3.12-slim, 3.12.15); bump it deliberately.
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PLEXUS_QUERIES_DIR=/app/queries \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    PLEXUS_EMBED_CACHE=/opt/fastembed \
    PLEXUS_EMBED_THREADS=1 \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1

RUN pip install --no-cache-dir uv==0.12.5

# The runtime user owns /app and /opt/fastembed from the start, so nothing needs a recursive chown afterwards
# (a chown -R over the venv would copy it into a second layer and double the image).
RUN useradd --create-home --uid 10001 plexus \
    && mkdir -p /app /opt/fastembed \
    && chown plexus:plexus /app /opt/fastembed
WORKDIR /app
USER plexus
# Dependencies first (cached layer), then the project (editable, so queries/ resolves next to src/).
COPY --chown=plexus:plexus pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --chown=plexus:plexus src ./src
COPY --chown=plexus:plexus queries ./queries
RUN uv sync --frozen --no-dev

# Bake the embedding model (int8 bge-small, ~67 MB) so nothing is downloaded at runtime (S2).
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')"

VOLUME ["/opt/fastembed"]

EXPOSE 8765 8080
# Default: the MCP server over streamable HTTP. The View API overrides the command (see docker-compose.yml).
CMD ["plexus-mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
