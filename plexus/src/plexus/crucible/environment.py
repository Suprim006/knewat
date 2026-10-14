"""Facts about where a run happened, recorded next to its numbers (FALKORDB_ARGS, versions, docker or not)."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

CONFIG_KEYS = (
    "TIMEOUT_MAX",
    "TIMEOUT_DEFAULT",
    "MAX_QUEUED_QUERIES",
    "RESULTSET_SIZE",
    "QUERY_MEM_CAPACITY",
    "THREAD_COUNT",
    "CACHE_SIZE",
    "OMP_THREAD_COUNT",
)


def in_docker() -> bool:
    return Path("/.dockerenv").exists() or os.environ.get("CRUCIBLE_IN_DOCKER") == "1"


def git_commit() -> str:
    env = os.environ.get("CRUCIBLE_GIT_COMMIT")
    if env:
        return env
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return os.environ.get("CRUCIBLE_GIT_COMMIT", "")


def falkordb_info(host: str, port: int) -> dict[str, Any]:
    """Server version and the effective module configuration (what ``FALKORDB_ARGS`` really resulted in)."""
    info: dict[str, Any] = {"host": host, "port": port, "reachable": False}
    try:
        import redis

        r = redis.Redis(host=host, port=port, decode_responses=True, socket_timeout=10)
        server = r.info("server")
        info.update(
            reachable=True,
            redis_version=server.get("redis_version"),
            os=server.get("os"),
            falkordb_args_env=os.environ.get("FALKORDB_ARGS", ""),
        )
        try:
            modules = r.execute_command("MODULE", "LIST")
            info["modules"] = [
                m if isinstance(m, dict) else dict(zip(m[::2], m[1::2], strict=False)) for m in modules
            ]
        except Exception:  # noqa: BLE001 - informational only
            info["modules"] = []
        cfg: dict[str, Any] = {}
        for key in CONFIG_KEYS:
            try:
                resp = r.execute_command("GRAPH.CONFIG", "GET", key)
                cfg[key] = resp[1] if isinstance(resp, list) and len(resp) == 2 else resp
            except Exception:  # noqa: BLE001 - a key this build does not know is simply not recorded
                continue
        info["graph_config"] = cfg
        r.close()
    except Exception as exc:  # noqa: BLE001
        info["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return info


def collect(host: str, port: int, embedder: str) -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "in_docker": in_docker(),
        "git_commit": git_commit(),
        "embedder": embedder,
        "falkordb": falkordb_info(host, port),
    }
