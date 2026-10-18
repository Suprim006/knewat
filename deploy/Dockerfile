# Plexus one-container public deployment (Render Free, 512 MB): FalkorDB + plexus-api (with the Cypher console) + static
# plexus-view. No MCP server, no embedding model (D-016).
# Build context: the REPO ROOT (needs plexus/ and plexus-view/):   docker build -f deploy/Dockerfile -t plexus-deploy .
#
# Why python:3.12-slim + the FalkorDB files copied out of the official image, instead of building FROM falkordb:
#   falkordb/falkordb:6.0.2 is 488 MB (Debian 13 + redis + falkordb.so + a bundled Node browser) and has no Python, so we
#   would still have to add ~230 MB of Python/uv/ML wheels on top. redis-server (4.9 MB) and falkordb.so (62 MB) only
#   need libssl3/libz/libzstd/libstdc++, all present in python:3.12-slim (same Debian 13 base), so we take just those
#   two files. Same module build, same redis, no Node browser, and the base image is the digest-pinned one plexus/Dockerfile uses.

# ---- 1. plexus-view, built statically. VITE_PLEXUS_API=/ makes every call same-origin (/api/...). ----------------------
FROM node:24-slim AS view
WORKDIR /src
COPY plexus-view/package.json plexus-view/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY plexus-view/ ./
ENV VITE_PLEXUS_API=/
RUN npm run build

# ---- 2. FalkorDB 6.0.2 files (copied in stage 4) ------------------------------------------------------------------
FROM falkordb/falkordb:6.0.2 AS falkordb

# ---- 3. Python venv (no dev deps) ---------------------------------------------------------------------------------
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS py
ENV UV_LINK_MODE=copy UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1 UV_PROJECT_ENVIRONMENT=/app/.venv \
    HF_HUB_DISABLE_SYMLINKS_WARNING=1
RUN pip install --no-cache-dir uv==0.12.5
WORKDIR /app
COPY plexus/pyproject.toml plexus/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY plexus/src ./src
COPY plexus/queries ./queries
RUN uv sync --frozen --no-dev

# ---- 4. runtime ---------------------------------------------------------------------------------------------------
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH=/app/.venv/bin:$PATH \
    MALLOC_ARENA_MAX=2 \
    PLEXUS_QUERIES_DIR=/app/queries \
    PLEXUS_STATIC_DIR=/app/view \
    PLEXUS_RESULTS_DIR=/app/results \
    PLEXUS_EMBEDDER=hash \
    PLEXUS_DB_POOL=32 \
    PLEXUS_API_MAX_STREAMS=8 \
    FALKORDB_SO=/opt/falkordb/falkordb.so \
    PORT=10000

RUN useradd --create-home --uid 10001 plexus
COPY --from=falkordb /usr/local/bin/redis-server /usr/local/bin/redis-server
COPY --from=falkordb /var/lib/falkordb/bin/falkordb.so /opt/falkordb/falkordb.so
COPY --from=py /app /app
COPY --from=view /src/dist /app/view
# Only the two recordings that are restored on boot (plexus demo replay), and the Crucible results for /api/results
# (latest-all.json when P5 has produced it, else latest.json; the app picks).
COPY plexus/demo_data/recordings/acme-claude-sonnet /app/demo_data/recordings/acme-claude-sonnet
COPY plexus/demo_data/recordings/acme-scripted /app/demo_data/recordings/acme-scripted
COPY plexus/src/plexus/crucible/results/latest*.json /app/results/
COPY deploy/__init__.py deploy/app.py deploy/guard.py deploy/entrypoint.py /app/deploy/

WORKDIR /app
USER plexus
EXPOSE 10000
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=6 \
  CMD ["python", "-c", "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/healthz?deep=1' % os.environ.get('PORT', '10000'), timeout=4)"]
CMD ["python", "-m", "deploy.entrypoint"]
