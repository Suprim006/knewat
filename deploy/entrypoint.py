"""Process supervisor for the one-container deployment (no systemd, no second Python process).

    1. start redis-server + the FalkorDB module on 127.0.0.1 (ephemeral: no AOF, no RDB; capped memory; noeviction)
    2. wait until ``loading:0``
    3. reseed: restore the recordings ``acme-claude-sonnet`` -> tenant ``demo`` and ``acme-scripted`` ->
       ``demo_scripted`` (what ``plexus demo replay <run> --tenant <t> --reset`` does), failing the boot if a
       restored inventory does not match the recording's meta.json
    4. start the idle sweeper thread (team_* graphs idle > 24 h are deleted)
    5. serve the combined ASGI app with uvicorn on 0.0.0.0:$PORT (Render sets PORT; default 10000)

If redis dies the whole process exits (the platform restarts the container, which reseeds); SIGTERM stops both.
"""

from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("plexus.deploy")

REDIS_BIN = os.environ.get("REDIS_BIN", "redis-server")
FALKORDB_SO = os.environ.get("FALKORDB_SO", "/opt/falkordb/falkordb.so")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
# compose's FALKORDB_ARGS, with the per-query memory cap lowered for a 512 MB box and 2 query threads.
FALKORDB_ARGS = os.environ.get(
    "FALKORDB_ARGS",
    "TIMEOUT_MAX 10000 TIMEOUT_DEFAULT 5000 MAX_QUEUED_QUERIES 100 RESULTSET_SIZE 100000 "
    "QUERY_MEM_CAPACITY 67108864 THREAD_COUNT 2",
)
REDIS_MAXMEMORY = os.environ.get("PLEXUS_REDIS_MAXMEMORY", "100mb")
SEED = (("acme-claude-sonnet", "demo"), ("acme-scripted", "demo_scripted"))  # (recording, tenant)


def redis_command() -> list[str]:
    return [
        REDIS_BIN,
        "--bind", "127.0.0.1",  # never reachable from outside the container
        "--port", str(REDIS_PORT),
        "--protected-mode", "yes",
        "--appendonly", "no",  # ephemeral disk on Render, and the demo is reseeded on every boot
        "--save", "",
        "--dir", "/tmp",
        "--maxmemory", REDIS_MAXMEMORY,
        "--maxmemory-policy", "noeviction",  # allkeys-* would evict whole graphs; refuse writes instead
        "--loadmodule", FALKORDB_SO, *shlex.split(FALKORDB_ARGS),
    ]  # fmt: skip


def start_redis() -> subprocess.Popen:
    cmd = redis_command()
    log.info("starting %s", " ".join(cmd[:1] + cmd[1:3]) + " ... (ephemeral, 127.0.0.1 only)")
    return subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)


def wait_loaded(proc: subprocess.Popen, timeout_s: float = 90.0) -> None:
    import redis

    r = redis.Redis(host="127.0.0.1", port=REDIS_PORT, socket_timeout=2)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"redis-server exited with {proc.returncode} during startup")
        try:
            if r.info("persistence").get("loading") == 0 and r.ping():
                return
        except redis.RedisError:
            pass
        time.sleep(0.1)
    raise SystemExit("redis did not finish loading in time")


def reseed(client) -> None:
    from plexus.demo.replay import replay

    for run, tenant in SEED:
        t0 = time.monotonic()
        res = replay(client, run, tenant, reset=True)
        inv = res["inventory"]
        log.info(
            "reseeded '%s' -> tenant '%s': %s nodes, %s edges, matches meta.json=%s (%.2fs)",
            run, tenant, inv["total_nodes"], inv["total_edges"], res["matches"], time.monotonic() - t0,
        )  # fmt: skip
        if not res["matches"]:
            raise SystemExit(f"recording '{run}' restored with a different inventory than its meta.json")


def watch(proc: subprocess.Popen) -> None:
    code = proc.wait()
    log.error("redis-server exited (%s): stopping so the platform restarts the container", code)
    os._exit(1)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    t0 = time.monotonic()
    proc = start_redis()
    stop = threading.Event()

    def shutdown(*_):
        stop.set()
        if proc.poll() is None:
            proc.terminate()

    signal.signal(signal.SIGTERM, lambda *_: (shutdown(), os._exit(0)))
    try:
        wait_loaded(proc)
        log.info("redis + FalkorDB ready in %.2fs", time.monotonic() - t0)
        threading.Thread(target=watch, args=(proc,), daemon=True, name="redis-watch").start()

        os.environ.setdefault("FALKORDB_HOST", "127.0.0.1")
        os.environ.setdefault("FALKORDB_PORT", str(REDIS_PORT))
        from plexus.graph.client import GraphClient

        client = GraphClient()
        reseed(client)

        from deploy.app import build_app
        from deploy.guard import GuardConfig

        cfg = GuardConfig.from_env()
        app, sweeper = build_app(client, cfg)
        threading.Thread(
            target=sweeper.run_forever, args=(cfg.sweep_interval_s, stop), daemon=True, name="idle-sweep"
        ).start()
        if os.environ.get("PLEXUS_PREWARM", "1") == "1":  # load the embedding model off the request path
            from plexus.mcp.server import _prewarm

            _prewarm(app.runtime)

        import uvicorn

        port = int(os.environ.get("PORT", "10000"))
        log.info("boot complete in %.2fs; serving on 0.0.0.0:%d", time.monotonic() - t0, port)
        uvicorn.run(
            app,
            host="0.0.0.0",  # noqa: S104 - the public listener; redis stays on 127.0.0.1
            port=port,
            log_level="info",
            timeout_keep_alive=5,
            limit_concurrency=int(os.environ.get("PLEXUS_MAX_CONCURRENCY", "64")),
        )
    finally:
        shutdown()
        if proc.poll() is None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
