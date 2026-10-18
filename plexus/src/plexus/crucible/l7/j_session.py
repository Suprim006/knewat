"""Family J: the session model. Replays recorded agent call sequences with seeded, always-valid arguments.

Backend-neutral: a *session* talks to an adapter (``j_arms``) that exposes the same logical operations on every arm.

Where the sequences come from
-----------------------------
``demo_data/recordings/{acme-claude-sonnet,pilot-haiku}/calls.json``: one list of tool names per recorded agent
(planner / researcher / builder in each run: six sequences, 100 calls). A session picks one sequence uniformly
(seeded). Uniform choice over the six sequences reproduces the pooled mix of the 100 recorded calls exactly.

Argument synthesis (all from ``random.Random(SEED + k)``)
---------------------------------------------------------
* subjects / values / recall queries are drawn from a fixed vocabulary, so recalls hit and assertions collide (dups,
  supersedes and contradictions happen as in real use);
* ids always exist: a session only passes ids it created, ids a recall returned, or ids from its tenant's *pool*
  (seeded by ``preload`` before the cell and extended by every session of the same driver process);
* ``complete_task`` is replayed only if the session holds a successful claim (otherwise it is skipped, not counted);
* the tenant's task supply: ``preload`` creates ``seed_tasks`` tasks; every replayed ``create_tasks`` adds 6 tasks
  (the recorded batches); and a **refill rule**: a ``claim_next_task`` that finds nothing is immediately followed by
  one extra ``create_tasks`` of 6 tasks, counted as the separate tool ``create_tasks_refill``. Same rule on every arm.
"""

from __future__ import annotations

import json
import random
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from plexus.crucible.api import ClaimConflict
from plexus.crucible.l7.common import DEMO, SEED

RECORDINGS = DEMO.parent.parent / "recordings"  # plexus/demo_data/recordings
RUNS = ("acme-claude-sonnet", "pilot-haiku")
BATCH = 6  # tasks per create_tasks (the recorded planner batches have 6 tasks)
TRAV_RATE = 0.10  # J-trav: share of calls replaced by why / impact
POOL_CAP = 400
PREDICATES = (
    "uses",
    "owner",
    "status",
    "depends-on",
    "version",
    "risk",
    "decision",
    "region",
    "latency",
    "budget",
)

MIXES = ("J-real", "J-trav")
RECORDED_MIX = {  # the pre-registration's quoted percentages (checked in tests against the recordings)
    "start_session": 20,
    "recall": 16,
    "claim_next_task": 16,
    "complete_task": 14,
    "add_source": 8,
    "assert_fact": 8,
    "remember_episode": 5,
    "record_decision": 5,
    "handoff": 4,
    "create_tasks": 3,
    "verify_artifact": 1,
}


def load_sequences(root=RECORDINGS) -> dict[str, list[str]]:
    """``{"acme-claude-sonnet/planner": [tool, ...], ...}`` in recorded order, in a stable key order."""
    out: dict[str, list[str]] = {}
    for run in RUNS:
        calls = json.loads((root / run / "calls.json").read_text(encoding="utf-8"))
        by: dict[str, list[tuple[int, str]]] = {}
        for c in calls:
            by.setdefault(c["agent"], []).append((c["step"], c["tool"]))
        for agent in sorted(by):
            out[f"{run}/{agent}"] = [t for _, t in sorted(by[agent])]
    return out


def _vocab() -> tuple[list[str], list[str]]:
    r = random.Random(SEED)
    syl = ["ka", "lo", "mi", "ra", "te", "su", "vo", "ni", "pa", "do", "xe", "bu"]
    words = sorted({"".join(r.choice(syl) for _ in range(3)) for _ in range(400)})[:160]
    return words[:40], words  # nouns (subjects), all words (values, queries)


NOUNS, WORDS = _vocab()


@dataclass
class TenantPool:
    """Ids known to exist in one tenant. Thread-safe, bounded; shared by every session of this process."""

    facts: deque = field(default_factory=lambda: deque(maxlen=POOL_CAP))
    sources: deque = field(default_factory=lambda: deque(maxlen=POOL_CAP))
    decisions: deque = field(default_factory=lambda: deque(maxlen=POOL_CAP))
    artifacts: deque = field(default_factory=lambda: deque(maxlen=POOL_CAP))
    anchor_tasks: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_manifest(cls, man: dict[str, Any]) -> TenantPool:
        p = cls()
        for k in ("facts", "sources", "decisions", "artifacts"):
            getattr(p, k).extend(man.get(k, []))
        p.anchor_tasks = list(man["anchor_tasks"])
        p.agents = list(man["agents"])
        return p

    def add(self, kind: str, ident: str) -> None:
        with self.lock:
            getattr(self, kind).append(ident)

    def pick(self, kind: str, rng: random.Random) -> str | None:
        with self.lock:
            seq = getattr(self, kind)
            return seq[rng.randrange(len(seq))] if seq else None


# ------------------------------------------------------------------------------------------------ call classes
def classify_error(exc: BaseException) -> str:
    """Error class of a failed call (pre-registered classes + ``connection`` / ``unknown_ref`` split out of 'other')."""
    s = f"{type(exc).__name__}: {exc}".lower()
    if "max pending queries" in s:
        return "max_pending"
    if "database is locked" in s or "database table is locked" in s or "busy" in s:
        return "locked"
    if "no connection available" in s or "maxconnections" in s or "too many connections" in s:
        return "pool"
    if "timed out" in s or "timeout" in s or "interrupted" in s:
        return "timeout"
    if isinstance(exc, ConnectionError) or "connection" in s or "socket" in s:
        return "connection"
    if "unknownreference" in s or "unknown " in s:
        return "unknown_ref"
    return "other"


@dataclass
class Rec:
    """One thread's measurements (merged by the worker at the end; no lock needed while measuring)."""

    calls: list[tuple[str, float, float, str]] = field(default_factory=list)  # tool, t_start, ms, status
    sessions: int = 0
    skipped_complete: int = 0
    err_samples: dict[str, list[str]] = field(default_factory=dict)


class Session:
    """One replayed agent session against one tenant."""

    def __init__(
        self,
        adapter: Any,
        pool: TenantPool,
        rng: random.Random,
        agent: str,
        seq: list[str],
        trav: bool,
        rec: Rec,
        measuring: Callable[[], bool],
        alive: Callable[[], bool],
    ):
        self.a, self.pool, self.rng, self.agent, self.seq, self.trav = adapter, pool, rng, agent, seq, trav
        self.rec, self.measuring, self.alive = rec, measuring, alive
        self.held: list[tuple[str, int]] = []  # (task id, version) of successful claims not yet completed
        self.sid: str | None = None
        self.sources: list[str] = []
        self.facts: list[str] = []
        self.n = 0  # counter for unique ids

    # -- plumbing ---------------------------------------------------------------------------------------------
    def _timed(self, tool: str, fn: Callable[[], Any]) -> tuple[Any, bool]:
        """Run ``fn``; record (tool, start, ms, status) when measuring. Returns (result, ok)."""
        t0 = time.time()
        p0 = time.perf_counter()
        status, res = "ok", None
        try:
            res = fn()
        except ClaimConflict:
            status = "claim_conflict"
        except Exception as exc:
            status = "err:" + classify_error(exc)
            if self.measuring():
                s = self.rec.err_samples.setdefault(status, [])
                if len(s) < 3:
                    s.append(f"{tool}: {type(exc).__name__}: {str(exc)[:300]}")
        ms = (time.perf_counter() - p0) * 1000
        if self.measuring():
            self.rec.calls.append((tool, t0, ms, status))
        return res, status == "ok"

    def _uid(self) -> str:
        self.n += 1
        return f"{self.agent}n{self.n}"

    def _words(self, k: int) -> str:
        return " ".join(self.rng.choice(WORDS) for _ in range(k))

    def _task_batch(self) -> list[dict[str, Any]]:
        u = self._uid()
        out = []
        for i in range(BATCH):
            t: dict[str, Any] = {
                "id": f"tk_{u}_{i}",
                "title": f"task {self._words(3)}",
                "priority": self.rng.randrange(4),
            }
            if i in (1, 3, 5):  # three dependent tasks, as in the recorded DAGs
                t["depends_on"] = [f"tk_{u}_{i - 1}"]
            out.append(t)
        return out

    # -- one call ---------------------------------------------------------------------------------------------
    def call(self, tool: str) -> bool:
        """Replay one logical call. Returns False if the session must end (start_session failed)."""
        r, a, ag = self.rng, self.a, self.agent
        if tool == "start_session":
            sid, ok = self._timed(
                tool, lambda: a.start_session(ag, ("planner", "researcher", "builder")[r.randrange(3)])
            )
            if not ok:
                return False
            self.sid = sid
        elif tool == "create_tasks":
            batch = self._task_batch()
            self._timed(tool, lambda: a.create_tasks(batch))
        elif tool == "claim_next_task":
            res, ok = self._timed(tool, lambda: a.claim(ag))
            if ok and res is not None:
                self.held.append((res["id"], int(res["version"])))
            elif ok and res is None:  # no ready task: refill (identical rule on every arm)
                if self.rec.calls and self.rec.calls[-1][0] == tool and self.rec.calls[-1][3] == "ok":
                    c = self.rec.calls[-1]
                    self.rec.calls[-1] = (c[0], c[1], c[2], "no_task")
                batch = self._task_batch()
                self._timed("create_tasks_refill", lambda: a.create_tasks(batch))
        elif tool == "complete_task":
            if not self.held:
                self.rec.skipped_complete += 1
                return True
            tid, ver = self.held.pop()
            u = self._uid()
            arts = [{"kind": "note", "uri": f"mem://{u}", "hash": f"h{u}", "summary": self._words(4)}]
            res, ok = self._timed(tool, lambda: a.complete(ag, tid, ver, arts))
            if ok and res:
                for x in res:
                    self.pool.add("artifacts", x)
        elif tool == "recall":
            q = self._words(r.randrange(2, 4))
            res, ok = self._timed(tool, lambda: a.recall(ag, q))
            if ok and res:
                self.facts.extend(res[:3])
        elif tool == "record_decision":
            task = self.held[-1][0] if self.held else r.choice(self.pool.anchor_tasks)
            based = self._some_facts(r.randrange(0, 4))
            text = f"decision {self._words(5)}"
            res, ok = self._timed(tool, lambda: a.record_decision(ag, task, text, based))
            if ok and res:
                self.pool.add("decisions", res)
        elif tool == "add_source":
            uri = f"https://example.org/{self._uid()}"
            res, ok = self._timed(tool, lambda: a.add_source(uri))
            if ok and res:
                self.sources.append(res)
                self.pool.add("sources", res)
        elif tool == "assert_fact":
            subj = f"{r.choice(NOUNS)} {r.choice(NOUNS)}"
            pred = r.choice(PREDICATES)
            val = self._words(3)
            src = self.sources[-1] if self.sources else None
            derived = []
            if r.random() < 0.3:
                d = self.pool.pick("facts", r)
                if d:
                    derived = [d]
            res, ok = self._timed(tool, lambda: a.assert_fact(ag, subj, pred, val, src, derived))
            if ok and res:
                self.facts.append(res)
                self.pool.add("facts", res)
        elif tool == "remember_episode":
            text = f"episode {self._words(8)}"
            self._timed(tool, lambda: a.remember_episode(ag, self.sid, text))
        elif tool == "handoff":
            task = self.held[-1][0] if self.held else r.choice(self.pool.anchor_tasks)
            to = r.choice(self.pool.agents)
            arts = [x for x in [self.pool.pick("artifacts", r)] if x]
            facts = self._some_facts(r.randrange(0, 3))
            note = f"handoff {self._words(5)}"
            self._timed(tool, lambda: a.handoff(ag, to, task, note, arts, facts))
        elif tool == "verify_artifact":
            art = self.pool.pick("artifacts", r)
            if art is None:
                return True
            self._timed(tool, lambda: a.verify_artifact(ag, art))
        elif tool == "why":
            node = self.pool.pick("decisions", r) if r.random() < 0.5 else self.pool.pick("facts", r)
            node = node or self.pool.pick("facts", r)
            self._timed(tool, lambda: a.why(ag, node))
        elif tool == "impact":
            kind = "source" if r.random() < 0.5 else "fact"
            node = self.pool.pick("sources" if kind == "source" else "facts", r)
            self._timed(tool, lambda: a.impact(ag, kind, node))
        else:  # pragma: no cover - the recordings only contain the tools above
            raise ValueError(f"unknown tool {tool}")
        return True

    def _some_facts(self, k: int) -> list[str]:
        out: list[str] = []
        for _ in range(k):
            f = (
                self.facts[self.rng.randrange(len(self.facts))]
                if self.facts and self.rng.random() < 0.6
                else None
            )
            f = f or self.pool.pick("facts", self.rng)
            if f and f not in out:
                out.append(f)
        return out

    def run(self) -> None:
        for i, tool in enumerate(self.seq):
            if not self.alive():
                return
            if self.trav and i > 0 and self.rng.random() < TRAV_RATE:
                tool = "why" if self.rng.random() < 0.5 else "impact"
            if not self.call(tool):
                return
        self.rec.sessions += 1


# ------------------------------------------------------------------------------------------------ preload
def preload(adapter: Any, tenant: str, k: int, seed_tasks: int, n_facts: int = 24) -> dict[str, Any]:
    """Seed one tenant (not measured): agents, sources, facts, decisions, anchor tasks, artifacts, task supply.

    Returns the manifest (ids) the driver processes use to build their :class:`TenantPool`.
    """
    r = random.Random(SEED + 900_000 + k)
    agents = [f"seedagent{i}" for i in range(3)]
    for a in agents:
        adapter.start_session(a, "seed")
    sources = [adapter.add_source(f"https://example.org/{tenant}/seed{i}") for i in range(4)]
    facts: list[str] = []
    for i in range(n_facts):
        derived = [facts[-1]] if facts and i % 3 != 2 else []  # fact ids only (the F arm's Crucible check)
        facts.append(
            adapter.assert_fact(
                agents[i % 3],
                f"{r.choice(NOUNS)} {r.choice(NOUNS)}",
                r.choice(PREDICATES),
                " ".join(r.choice(WORDS) for _ in range(3)),
                sources[i % 4],
                derived,
            )
        )
    anchors = [f"anchor_{k}_{i}" for i in range(4)]
    adapter.create_tasks([{"id": a, "title": f"anchor {i}", "priority": 100} for i, a in enumerate(anchors)])
    artifacts: list[str] = []
    for i in range(4):
        t = adapter.claim(agents[0])
        assert t is not None, "anchor claim failed"
        artifacts += adapter.complete(
            agents[0],
            t["id"],
            int(t["version"]),
            [{"kind": "note", "uri": f"mem://{tenant}/a{i}", "hash": f"x{i}", "summary": "seed"}],
        )
    decisions = [
        adapter.record_decision(agents[0], anchors[i % 4], f"seed decision {i}", facts[i * 3 : i * 3 + 3])
        for i in range(6)
    ]
    for lo in range(0, seed_tasks, 500):
        n = min(500, seed_tasks - lo)
        adapter.create_tasks(
            [
                {
                    "id": f"seed_{k}_{lo + i}",
                    "title": f"seed task {lo + i}",
                    "priority": r.randrange(4),
                    **({"depends_on": [f"seed_{k}_{lo + i - 1}"]} if i % 5 == 4 else {}),
                }
                for i in range(n)
            ]
        )
    return {
        "tenant": tenant,
        "agents": agents,
        "sources": sources,
        "facts": facts,
        "decisions": decisions,
        "artifacts": artifacts,
        "anchor_tasks": anchors,
        "seed_tasks": seed_tasks,
    }
