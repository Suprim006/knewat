"""Shared harness: environment/config, per-arm run context (tenants + cleanup), thread helpers, aggregation."""

from __future__ import annotations

import contextlib
import os
import shutil
import statistics
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plexus.crucible.api import BackendSpec, CoordinationBackend, Unsupported
from plexus.crucible.backends import open_backend


@dataclass
class Env:
    """Where the arms live: a scratch dir for the file arms, a FalkorDB endpoint for the Plexus arms."""

    root: str
    host: str = "127.0.0.1"
    port: int = 6379
    embedder: str = "fastembed"

    @classmethod
    def from_environ(cls, root: str | None = None, embedder: str | None = None) -> Env:
        return cls(
            root=root or tempfile.mkdtemp(prefix="crucible-"),
            host=os.environ.get("FALKORDB_HOST") or "127.0.0.1",
            port=int(os.environ.get("FALKORDB_PORT") or 6379),
            embedder=embedder or os.environ.get("PLEXUS_EMBEDDER") or "fastembed",
        )

    def spec(self, arm: str, tenant: str, **options: Any) -> BackendSpec:
        return BackendSpec(
            arm=arm,
            tenant=tenant,
            root=self.root,
            host=self.host,
            port=self.port,
            embedder=self.embedder,
            options=options,
        )


def new_tenant(tag: str) -> str:
    return f"{tag}_{uuid.uuid4().hex[:10]}"[:48]


class ArmRun:
    """Opens tenant stores for one arm during one test run and removes everything afterwards."""

    def __init__(self, env: Env, arm: str):
        self.env, self.arm = env, arm
        self._opened: list[CoordinationBackend] = []
        self._dirs: list[Path] = []

    def spec(self, tag: str = "t", tenant: str | None = None) -> BackendSpec:
        return self.env.spec(self.arm, tenant or new_tenant(tag))

    def open(self, tag: str = "t", tenant: str | None = None) -> CoordinationBackend:
        spec = self.spec(tag, tenant)
        b = open_backend(spec)
        self._opened.append(b)
        return b

    def cleanup(self) -> None:
        for b in self._opened:
            drop = getattr(b, "drop", None)  # Plexus arms: delete the tenant graph first, then disconnect
            if drop is not None:
                with contextlib.suppress(Exception):
                    drop()
            with contextlib.suppress(Exception):
                b.close()
            d = getattr(b, "dir", None)
            if d is not None:
                shutil.rmtree(d, ignore_errors=True)
        self._opened.clear()

    def __enter__(self) -> ArmRun:
        return self

    def __exit__(self, *exc: object) -> None:
        self.cleanup()


def run_workers(
    n: int, fn: Callable[[int], None], *, together: bool = True, timeout: float = 600.0
) -> list[BaseException]:
    """Run ``fn(i)`` for i in range(n) on n threads (released together by a barrier). Returns the exceptions."""
    errors: list[BaseException] = []
    lock = threading.Lock()
    barrier = threading.Barrier(n) if together and n > 1 else None

    def runner(i: int) -> None:
        try:
            if barrier is not None:
                barrier.wait(timeout=timeout)
            fn(i)
        except BaseException as exc:  # noqa: BLE001 - reported to the caller, never swallowed
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=runner, args=(i,), daemon=True) for i in range(n)]
    for t in threads:
        t.start()
    deadline = time.monotonic() + timeout
    for t in threads:
        t.join(max(0.0, deadline - time.monotonic()))
    alive = sum(t.is_alive() for t in threads)
    if alive:
        errors.append(TimeoutError(f"{alive} worker thread(s) still running after {timeout:.0f}s"))
    return errors


@dataclass
class RunResult:
    """One execution of one test case for one arm."""

    seed: int
    params: dict[str, Any] = field(default_factory=dict)
    violations: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    passed: bool = True
    unsupported: str = ""
    errors: list[str] = field(default_factory=list)
    error_total: int = 0  # raw number of exceptions (``errors`` is grouped by message)
    duration_s: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def set_errors(self, excs: Iterable[BaseException]) -> None:
        excs = list(excs)
        self.errors = describe_errors(excs)
        self.error_total = len(excs)

    def finish(self) -> RunResult:
        if self.errors:
            self.violations["errors"] = self.error_total or len(self.errors)
        self.passed = not self.unsupported and all(v == 0 for v in self.violations.values())
        return self

    def to_json(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "params": self.params,
            "passed": self.passed,
            "violations": self.violations,
            "metrics": self.metrics,
            "unsupported": self.unsupported,
            "errors": self.errors[:5],
            "duration_s": round(self.duration_s, 3),
            "details": self.details,
        }


def describe_errors(errors: Iterable[BaseException], limit: int = 5) -> list[str]:
    """Distinct messages with how many times each occurred, e.g. ``'X: boom (x100)'``."""
    counts: dict[str, int] = {}
    for e in errors:
        msg = f"{type(e).__name__}: {e}"[:300]
        counts[msg] = counts.get(msg, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
    return [m if n == 1 else f"{m} (x{n})" for m, n in ranked]


def unsupported_result(seed: int, params: dict[str, Any], exc: Unsupported) -> RunResult:
    return RunResult(seed=seed, params=params, unsupported=str(exc)).finish()


def aggregate(runs: Sequence[RunResult]) -> dict[str, Any]:
    """Counts, not averages, for violations: totals per violation key plus the number of failing runs."""
    totals: dict[str, int] = {}
    for r in runs:
        for k, v in r.violations.items():
            totals[k] = totals.get(k, 0) + int(v)
    metrics: dict[str, dict[str, float]] = {}
    keys = {
        k
        for r in runs
        for k, v in r.metrics.items()
        if isinstance(v, int | float) and not isinstance(v, bool)
    }
    for k in sorted(keys):
        vals = [float(r.metrics[k]) for r in runs if k in r.metrics]
        metrics[k] = {
            "min": min(vals),
            "median": statistics.median(vals),
            "max": max(vals),
            "sum": sum(vals),
        }
    unsupported = sorted({r.unsupported for r in runs if r.unsupported})
    return {
        "runs": len(runs),
        "runs_passed": sum(r.passed for r in runs),
        "passed": bool(runs) and all(r.passed for r in runs),
        "unsupported": unsupported[0] if unsupported else "",
        "violations_total": totals,
        "metrics": metrics,
    }
