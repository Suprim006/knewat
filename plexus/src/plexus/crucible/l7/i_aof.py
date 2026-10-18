"""Family I3 extra: reproduce the slot-64 AOF-replay crash from the preserved data directory, then bisect the AOF.

Only ONE extra container is used: ``plexus-db-71-aofrepro`` on 127.0.0.1:6371 (image falkordb/falkordb:6.0.2, the same env
as ``scripts/agent_db.sh``). The original data directory is never mounted or modified: every attempt works on a COPY that
is ``docker cp``-ed into a created-but-not-started container. The container is removed at the end.

Bisection: the incremental AOF is parsed as RESP; prefixes cut at command boundaries are loaded, and the smallest
crashing command-prefix is searched for (assumes "any prefix that contains the culprit crashes", checked at the end).
"""

from __future__ import annotations

import re
import shutil
import tempfile
import time
from functools import partial
from pathlib import Path
from typing import Any

from plexus.crucible.l7.common import docker

NAME = "plexus-db-71-aofrepro"
IMAGE = "falkordb/falkordb:6.0.2"
ENV = [
    "REDIS_ARGS=--appendonly yes --maxmemory-policy noeviction",
    "FALKORDB_ARGS=TIMEOUT_MAX 10000 TIMEOUT_DEFAULT 5000 MAX_QUEUED_QUERIES 500 RESULTSET_SIZE 100000 QUERY_MEM_CAPACITY 268435456",
]


_d = partial(docker, timeout=300)


def remove() -> None:
    _d("rm", "-f", NAME)


def attempt(data: Path, wait_s: float = 90.0) -> dict[str, Any]:
    """Load a copy of ``data`` into a fresh container; returns {crashed, ready, signature, seconds}."""
    remove()
    args = ["create", "--name", NAME, "-p", "127.0.0.1:6371:6379"]
    for e in ENV:
        args += ["-e", e]
    cr = _d(*args, IMAGE)
    if cr.returncode:
        raise RuntimeError(f"docker create failed: {cr.stderr[:200]}")
    cp = _d("cp", f"{data.as_posix()}/.", f"{NAME}:/var/lib/falkordb/data/")
    if cp.returncode:
        raise RuntimeError(f"docker cp failed: {cp.stderr[:200]}")
    t0 = time.time()
    _d("start", NAME)
    res: dict[str, Any] = {"crashed": False, "ready": False, "signature": None}
    while time.time() - t0 < wait_s:
        lg = _d("logs", NAME)
        log = lg.stdout + lg.stderr
        if "REDIS BUG REPORT START" in log:
            res["crashed"] = True
            m = re.search(r"(Guru Meditation[^\n]*|crashed by signal: \d+[^\n]*)", log)
            res["signature"] = m.group(1)[:160] if m else "bug report"
            eip = re.search(r"EIP:\n([^\n]*)", log)
            res["eip"] = eip.group(1)[:120] if eip else None
            res["in_aof_load"] = "loadSingleAppendOnlyFile" in log
            break
        if re.search(r"DB loaded from append only file", log):
            res["ready"] = True
            break
        time.sleep(1.0)
    res["seconds"] = round(time.time() - t0, 1)
    if not res["crashed"] and not res["ready"]:
        res["note"] = "neither crashed nor finished loading within the wait"
    return res


def resp_offsets(path: Path) -> list[int]:
    """Byte offsets just AFTER each complete RESP command in an AOF file (command boundaries)."""
    buf = path.read_bytes()
    pos, out, n = 0, [], len(buf)
    while pos < n:
        if buf[pos : pos + 1] != b"*":
            break  # annotation lines or a cut tail: stop at the last good boundary
        eol = buf.index(b"\r\n", pos)
        argc = int(buf[pos + 1 : eol])
        p = eol + 2
        for _ in range(argc):
            eol = buf.index(b"\r\n", p)
            ln = int(buf[p + 1 : eol])
            p = eol + 2 + ln + 2
        if p > n:
            break
        pos = p
        out.append(pos)
    return out


def _variant(data: Path, tmp: Path, incr_bytes: bytes) -> Path:
    d = tmp / "v"
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(data, d)
    (d / "appendonlydir" / "appendonly.aof.2.incr.aof").write_bytes(incr_bytes)
    return d


def run_repro(
    data: Path, repeats: int = 3, bisect: bool = True, max_steps: int = 20, rate_n: int = 8
) -> dict[str, Any]:
    out: dict[str, Any] = {"data_dir": str(data), "container": NAME, "attempts": []}
    tmp = Path(tempfile.mkdtemp(prefix="aofrepro-"))
    try:
        work = tmp / "full"
        shutil.copytree(data, work)  # a COPY; the original is never touched
        incr = work / "appendonlydir" / "appendonly.aof.2.incr.aof"
        for i in range(repeats):
            r = attempt(work)
            out["attempts"].append(r)
            print(f"AOF repro attempt {i + 1}: {r}", flush=True)
        crashes = sum(1 for a in out["attempts"] if a["crashed"])
        out["summary"] = {
            "attempts": repeats,
            "crashed": crashes,
            "signatures": sorted({a["signature"] for a in out["attempts"] if a["signature"]}),
        }
        if bisect and crashes:
            offs = resp_offsets(incr)
            out["incr_commands"] = len(offs)
            out["incr_bytes"] = incr.stat().st_size
            raw = incr.read_bytes()
            lo, hi = (
                0,
                len(offs),
            )  # hi crashes (full file); find the smallest crashing prefix length in commands
            steps: list[dict[str, Any]] = []
            while hi - lo > 1 and len(steps) < max_steps:
                mid = (lo + hi) // 2
                r = attempt(_variant(work, tmp, raw[: offs[mid - 1]]), wait_s=60)
                steps.append(
                    {"commands": mid, "bytes": offs[mid - 1], "crashed": r["crashed"], "ready": r["ready"]}
                )
                print(f"AOF bisect: {steps[-1]}", flush=True)
                if r["crashed"]:
                    hi = mid
                else:
                    lo = mid
            out["bisect_steps"] = steps
            out["smallest_crashing_prefix_commands"] = hi
            out["largest_clean_prefix_commands"] = lo
            if hi - lo == 1 and hi >= 1:
                start = offs[hi - 2] if hi >= 2 else 0
                cmd = raw[start : offs[hi - 1]].decode("utf-8", "replace")
                out["culprit_command_index"] = hi
                out["culprit_command_head"] = cmd.replace("\r\n", " | ")[:400]
                if hi >= 2:
                    out["confirm_prefix_without_culprit_crashed"] = attempt(
                        _variant(work, tmp, raw[: offs[hi - 2]]), wait_s=60
                    )["crashed"]
                out["culprit_alone_crashed"] = attempt(
                    _variant(work, tmp, raw[start : offs[hi - 1]]), wait_s=60
                )["crashed"]
            else:
                out["note"] = "bisection stopped by max_steps before reaching one command"
            # the crash is not deterministic (see the bisect), so measure how often it happens on the full file and
            # on the largest prefix the bisection saw load cleanly
            if rate_n:
                lo_n = out.get("largest_clean_prefix_commands", 0)
                prefix = _variant(work, tmp, raw[: offs[lo_n - 1]]) if lo_n else None
                full = [attempt(work)["crashed"] for _ in range(rate_n)]
                out["rate_full_file"] = {"attempts": rate_n, "crashed": sum(full)}
                if prefix is not None:
                    part = [attempt(prefix, wait_s=60)["crashed"] for _ in range(rate_n)]
                    out["rate_largest_clean_prefix"] = {
                        "commands": lo_n,
                        "attempts": rate_n,
                        "crashed": sum(part),
                    }
    finally:
        remove()
        shutil.rmtree(tmp, ignore_errors=True)
    return out


if __name__ == "__main__":
    import json
    import sys

    res = run_repro(Path(sys.argv[1]), repeats=int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    print(json.dumps(res, indent=1))
