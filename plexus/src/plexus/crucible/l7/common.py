"""Shared helpers for Crucible L7 (P10: graph vs SQL strengths by scale). See docs/research/P10_GRAPH_VS_SQL.md.

Results envelope and writer follow L6 (``l6.run.envelope`` / ``write``) with schema ``crucible-l7/1`` and the output
directory ``plexus/demo_data/crucible/l7/``. Everything here is backend-neutral.
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from plexus.crucible import environment
from plexus.crucible.l6.run import git_state
from plexus.crucible.util import iso_utc, percentile, run_stamp

SEED = 20261016
TIMEOUT_MS = 10_000  # per-statement budget for every database arm (pre-registration "Conventions")
PKG = Path(__file__).resolve()
DEMO = PKG.parents[4] / "demo_data" / "crucible" / "l7"
DEFAULT_HOST = "127.0.0.1"  # "localhost" tries ::1 first on Windows + Docker


# ------------------------------------------------------------------------------------------------ results files
def envelope(kind: str, host: str, port: int, started: float, command: str) -> dict[str, Any]:
    """The common header of every L7 results.json (git state, machine, FalkorDB module config)."""
    return {
        "schema": "crucible-l7/1",
        "kind": kind,
        "run": {
            "id": run_stamp() + f"-{kind}",
            "started_at": iso_utc(started),
            "finished_at": "",
            "command": command,
            "llm_calls": 0,
            "cost_usd": 0.0,
        },
        "git": git_state(),
        "environment": environment.collect(host, port, "none"),
        "sqlite_version": sqlite3.sqlite_version,
        "seed": SEED,
        "timeout_ms": TIMEOUT_MS,
    }


def write(doc: dict[str, Any], out: Path | None = None, report: str | None = None) -> Path:
    """Write ``<out>/<run id>/results.json`` (+ ``report.md``) and copy it to ``<out>/latest-<kind>.json``."""
    out = out or DEMO
    doc["run"]["finished_at"] = iso_utc()
    d = out / doc["run"]["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(
        json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    if report is not None:
        (d / "report.md").write_text(report, encoding="utf-8", newline="\n")
    shutil.copyfile(d / "results.json", out / f"latest-{doc['kind']}.json")
    return d


# ------------------------------------------------------------------------------------------------ statistics
def lat_summary(xs: Iterable[float]) -> dict[str, Any]:
    v = list(xs)
    if not v:
        return {"n": 0, "p50": None, "p99": None, "max": None, "mean": None}
    return {
        "n": len(v),
        "p50": round(percentile(v, 50), 3),
        "p99": round(percentile(v, 99), 3),
        "max": round(max(v), 3),
        "mean": round(statistics.fmean(v), 3),
    }


def code_lines(text: str) -> int:
    """Non-blank, non-comment lines of a query text (Cypher ``//``, SQL ``--``) or Python (``#``)."""
    n = 0
    for ln in text.splitlines():
        s = ln.strip()
        if s and not s.startswith(("//", "--", "#")):
            n += 1
    return n


# ------------------------------------------------------------------------------------------------ SQLite budget
def sqlite_deadline(conn: sqlite3.Connection, timeout_ms: int = TIMEOUT_MS) -> Callable[[], None]:
    """Install a progress handler that aborts the running statement after ``timeout_ms``.

    Returns ``arm()``: call it right before each statement to (re)start the clock. An aborted statement raises
    ``sqlite3.OperationalError('interrupted')``, which callers count as a timeout.
    """
    state = {"until": float("inf")}

    def handler() -> int:
        return 1 if time.perf_counter() > state["until"] else 0

    conn.set_progress_handler(handler, 10_000)

    def arm() -> None:
        state["until"] = time.perf_counter() + timeout_ms / 1000

    return arm


# ------------------------------------------------------------------------------------------------ resources
class _PMC(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def process_resources() -> dict[str, Any]:
    """CPU seconds (user+system) and working set of THIS process; handle count on Windows. No psutil needed."""
    t = os.times()
    out: dict[str, Any] = {"cpu_s": round(t.user + t.system, 3)}
    if sys.platform == "win32":
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PMC), ctypes.c_ulong]
        k32.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        h = k32.GetCurrentProcess()
        pmc = _PMC()
        pmc.cb = ctypes.sizeof(_PMC)
        if k32.K32GetProcessMemoryInfo(h, ctypes.byref(pmc), pmc.cb):
            out["working_set_mb"] = round(pmc.WorkingSetSize / 2**20, 1)
            out["peak_working_set_mb"] = round(pmc.PeakWorkingSetSize / 2**20, 1)
        n = ctypes.c_ulong()
        if k32.GetProcessHandleCount(h, ctypes.byref(n)):
            out["handles"] = int(n.value)
    else:  # pragma: no cover - not this machine
        import resource

        out["peak_working_set_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    return out


def _parse_size(s: str) -> float:
    """'1.2GiB' / '512MiB' / '10kB' -> MiB."""
    s = s.strip()
    units = {"KiB": 1 / 1024, "kB": 1 / 1024, "MiB": 1, "MB": 1, "GiB": 1024, "GB": 1024, "B": 1 / 2**20}
    for u in sorted(units, key=len, reverse=True):
        if s.endswith(u):
            return float(s[: -len(u)]) * units[u]
    return float("nan")


def docker_stats_once(container: str) -> dict[str, Any] | None:
    """One ``docker stats --no-stream`` sample: CPU% and memory MiB of ``container`` (None if unavailable)."""
    try:
        out = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}}|{{.MemUsage}}", container],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout.strip()
        cpu, mem = out.split("|")
        return {"cpu_pct": float(cpu.rstrip("%")), "mem_mib": round(_parse_size(mem.split("/")[0]), 1)}
    except Exception:
        return None


class DockerSampler:
    """Background sampler of one container's CPU% / memory (``docker stats`` takes ~1-2 s per sample)."""

    def __init__(self, container: str, period_s: float = 1.0):
        self.container, self.period_s = container, period_s
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._loop, daemon=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            s = docker_stats_once(self.container)
            if s is not None:
                s["t"] = time.time()
                self.samples.append(s)
            self._stop.wait(self.period_s)

    def __enter__(self) -> DockerSampler:
        self._t.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stop.set()
        self._t.join(timeout=30)

    def summary(self) -> dict[str, Any]:
        cpu = [s["cpu_pct"] for s in self.samples]
        mem = [s["mem_mib"] for s in self.samples]
        if not cpu:
            return {"samples": 0}
        return {
            "samples": len(cpu),
            "cpu_pct_mean": round(statistics.fmean(cpu), 1),
            "cpu_pct_max": round(max(cpu), 1),
            "mem_mib_max": round(max(mem), 1),
            "mem_mib_last": round(mem[-1], 1),
        }


def container_for_port(port: int) -> str:
    """The docker container publishing 127.0.0.1:<port> (``plexus-db-<slot>`` for ``63<slot>``)."""
    return f"plexus-db-{str(port)[-2:]}" if str(port).startswith("63") else ""
