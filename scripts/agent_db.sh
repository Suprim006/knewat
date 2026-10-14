#!/usr/bin/env bash
# Per-agent FalkorDB container helper.
#   scripts/agent_db.sh <slot>      start (or reuse) plexus-db-<slot> on 127.0.0.1:63<slot>
#   scripts/agent_db.sh rm <slot>   remove it
# <slot> is a two-digit number (10..99). Never touches falkordb-dev or other slots.
set -euo pipefail

IMAGE="${PLEXUS_DB_IMAGE:-falkordb/falkordb:6.0.2}"
# Keep in sync with docker-compose.yml (FALKORDB_ARGS / REDIS_ARGS).
FALKORDB_ARGS_VALUE="TIMEOUT_MAX 10000 TIMEOUT_DEFAULT 5000 MAX_QUEUED_QUERIES 500 RESULTSET_SIZE 100000 QUERY_MEM_CAPACITY 268435456"
REDIS_ARGS_VALUE="--appendonly yes --maxmemory-policy noeviction"

usage() {
  echo "usage: $0 <slot> | $0 rm <slot>" >&2
  exit 2
}

check_slot() {
  [[ "$1" =~ ^[0-9]{2}$ ]] || { echo "slot must be two digits, got '$1'" >&2; exit 2; }
}

[[ $# -ge 1 ]] || usage

if [[ "$1" == "rm" ]]; then
  [[ $# -eq 2 ]] || usage
  check_slot "$2"
  docker rm -f "plexus-db-$2" >/dev/null 2>&1 || true
  echo "removed plexus-db-$2"
  exit 0
fi

[[ $# -eq 1 ]] || usage
SLOT="$1"
check_slot "$SLOT"
NAME="plexus-db-${SLOT}"
PORT="63${SLOT}"

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  if [[ "$(docker inspect -f '{{.State.Running}}' "$NAME")" != "true" ]]; then
    docker start "$NAME" >/dev/null
  fi
  echo "reusing $NAME on 127.0.0.1:${PORT}"
else
  docker run -d --name "$NAME" \
    -p "127.0.0.1:${PORT}:6379" \
    -e "REDIS_ARGS=${REDIS_ARGS_VALUE}" \
    -e "FALKORDB_ARGS=${FALKORDB_ARGS_VALUE}" \
    "$IMAGE" >/dev/null
  echo "started $NAME on 127.0.0.1:${PORT}"
fi

for _ in $(seq 1 60); do
  if [[ "$(docker exec "$NAME" redis-cli ping 2>/dev/null || true)" == "PONG" ]]; then
    echo "ready: PLEXUS_TEST_DB_PORT=${PORT}"
    exit 0
  fi
  sleep 0.5
done
echo "timeout waiting for $NAME" >&2
exit 1
