"""L8 runner: one arm x one seed of the S21 sprint with real ``claude -p`` agents (or a stand-in launcher in tests).

    python -m plexus.crucible.l8.run prepare --out DIR                      # schedule/sentinels for the 5 seeds ($0)
    python -m plexus.crucible.l8.run arm --seed 20261017 --arm P --out DIR  # one paid run
    python -m plexus.crucible.l8.run campaign --seeds 1 --arms P,B1,B0p --out DIR --budget-usd 25

Reused machinery (§2): ``ClaudeDriver`` (process handling, stream-json, kill, transcript sanitising) from
``plexus.demo.orchestrator``; the baseline MCP server (``crucible/l3/baseline_mcp.py``) for B1; ``play_scale`` (L2-scale)
for the 20-sprint history; the L5a renderer and ``ast`` truth through ``l8.repo``; ``plexus code hook-git`` for P.
What is new: the turn-boundary schedule (commits, kills K1-K3, v2), the file tools, the B0' arm (no MCP; the harness
is the lead), and the per-run record the deterministic scorer reads.

Arms: ``P`` (plexus-mcp stdio, FalkorDB tenant graph, post-commit hook -> mark_changed), ``B1`` (SQLite through the
baseline MCP, no staleness tools), ``B0p`` (B0': Claude Code with Read/Write/Edit/Glob/Grep and its own files).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plexus.crucible.l3.run import _result_json
from plexus.crucible.l8 import scenario as S
from plexus.crucible.l8.faults import SEEDS, all_tokens, build_schedule
from plexus.crucible.l8.repo import Edit, git, init_repo, initial_modules, land
from plexus.demo.engine import AgentKilled
from plexus.demo.orchestrator import (
    REAL_BUILDER_LEASE_MS,
    REAL_LEASE_MS,
    ClaudeConfig,
    ClaudeDriver,
    ClaudeRunError,
    TurnReport,
    plexus_mcp_command,
)

ARMS = ("P", "B1", "B0p")
MCP_PREFIX = "mcp__plexus__"
FILE_TOOLS = "Read,Write,Edit,Glob,Grep"
MCP_WRITES = frozenset(
    {"assert_fact", "record_decision", "handoff", "remember_episode", "add_source", "anchor_fact", "verify_fact",
     "complete_task", "create_tasks"}
)  # fmt: skip
B0P_LEASE_WAIT_S = 3.0
MAX_PROCESSES = 40
MAX_ATTEMPTS = 3
HOOK_PORT = int(os.environ.get("L8_HOOK_PORT", "8865"))
OUT_DEFAULT = Path(__file__).resolve().parents[4] / "demo_data" / "crucible" / "l8"
REPO_ROOT = Path(__file__).resolve().parents[5]


# ------------------------------------------------------------------------------------------------ envelope
def git_state() -> dict[str, Any]:
    """HEAD and whether the WHOLE repository differs from it (the l7 fix 05632f9, widened to the repo root).

    Paths under the L8 output directory are listed separately: results written by earlier runs of the same
    campaign are expected there and do not make the *code* dirty."""

    def g(*a: str) -> str:
        return subprocess.run(
            ["git", *a], capture_output=True, text=True, cwd=REPO_ROOT, timeout=30
        ).stdout.strip()

    lines = g("status", "--porcelain", "--untracked-files=all").splitlines()
    out_rels = ("plexus/demo_data/crucible/l8/", "plexus/demo_data/crucible/l8_postfix/")  # P12: + the re-run
    code = [x for x in lines if not any(r in x for r in out_rels)]
    return {
        "commit": g("rev-parse", "HEAD"),
        "short": g("rev-parse", "--short", "HEAD"),
        "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(code),
        "dirty_files": code[:30],
        "results_files_uncommitted": len(lines) - len(code),
    }


def claude_version() -> str:
    try:
        return subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=60
        ).stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return f"unknown ({type(exc).__name__})"


# ------------------------------------------------------------------------------------------------ prepare
def prepare(out: Path) -> dict[int, dict[str, Any]]:
    """schedule.json + sentinels.json for every seed, and scenario.json (briefs ``l8-v1``). Deterministic, $0."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "scenario.json").write_text(
        json.dumps(S.scenario_json(), indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    res = {}
    for seed in SEEDS:
        d = build_schedule(seed)
        sd = out / "seeds" / str(seed)
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "schedule.json").write_text(
            json.dumps(d["schedule"], indent=1) + "\n", encoding="utf-8", newline="\n"
        )
        (sd / "sentinels.json").write_text(
            json.dumps(d["sentinels"], indent=1) + "\n", encoding="utf-8", newline="\n"
        )
        res[seed] = d
    return res


def load_seed(out: Path, seed: int) -> tuple[dict[str, Any], dict[str, Any]]:
    sd = out / "seeds" / str(seed)
    return (json.loads((sd / "schedule.json").read_text(encoding="utf-8")),
            json.loads((sd / "sentinels.json").read_text(encoding="utf-8")))  # fmt: skip


# ------------------------------------------------------------------------------------------------ stores
class Store:
    """Harness-side view of an arm's task state (agents never see this) and the end-of-run dump."""

    def status(self, tid: str) -> dict[str, Any] | None: ...
    def dump(self) -> dict[str, Any]: ...
    def close(self) -> None: ...


class PlexusStore(Store):
    def __init__(self, tenant: str, host: str, port: int):
        from plexus.graph.client import GraphClient
        from plexus.graph.tenancy import graph_name
        from plexus.relay import Relay

        self.client = GraphClient(host=host, port=port)
        self.graph = graph_name(tenant)
        self.relay = Relay(self.client, self.graph)

    def status(self, tid: str) -> dict[str, Any] | None:
        return self.relay.task_status(tid)

    def q(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        return self.client.graph(self.graph).ro_query(cypher, params or {}).result_set

    def count_changes(self) -> int:
        return int(self.q("MATCH (c:Change) RETURN count(c)")[0][0])

    def dump(self) -> dict[str, Any]:
        facts = [
            dict(zip(("id", "subject", "predicate", "value", "status", "valid_from", "valid_to", "recorded_at",
                      "verify_state", "anchors"), r, strict=True))
            for r in self.q(
                "MATCH (f:Fact) OPTIONAL MATCH (f)-[:ABOUT]->(e:Entity) "
                "RETURN f.id, e.name, f.predicate, f.value, f.status, f.valid_from, f.valid_to, f.recorded_at, "
                "coalesce(f.verify_state, 'verified'), [(f)-[:ANCHORED_TO]->(a:CodeAnchor) | a.path + '#' + a.symbol]"
            )
        ]  # fmt: skip
        decisions = [
            {"id": r[0], "text": r[1], "at": r[2], "based_on": r[3]}
            for r in self.q(
                "MATCH (d:Decision) RETURN d.id, d.text, d.at, [(d)-[:BASED_ON]->(f:Fact) | f.id]"
            )
        ]
        handoffs = [
            {"id": r[0], "note": r[1], "fact_ids": r[2]}
            for r in self.q("MATCH (h:Handoff) RETURN h.id, h.note, [(h)-[:CARRIES]->(f:Fact) | f.id]")
        ]
        wrote = [
            {"node": r[0], "agent": r[1], "at": r[2]}
            for r in self.q("MATCH (s:Step)-[:WROTE]->(x) RETURN x.id, s.agent_id, s.at")
        ]
        reads = [
            {"agent": r[0], "at": r[1], "fact": r[2], "value": r[3]}
            for r in self.q("MATCH (s:Step)-[:READ]->(f:Fact) RETURN s.agent_id, s.at, f.id, f.value")
        ]
        changes = [
            {"id": r[0], "commit": r[1], "at": r[2], "suspected": r[3]}
            for r in self.q(
                "MATCH (c:Change) RETURN c.id, c.commit, c.at, [(c)-[:SUSPECTED]->(f:Fact) | f.id]"
            )
        ]
        tasks = [
            {"id": r[0], "status": r[1], "claimed_by": r[2], "version": r[3]}
            for r in self.q("MATCH (t:Task) RETURN t.id, t.status, t.claimed_by, t.version")
        ]
        return {"facts": facts, "decisions": decisions, "handoffs": handoffs, "wrote": wrote, "reads": reads,
                "changes": changes, "tasks": tasks}  # fmt: skip

    def close(self) -> None:
        self.client.close()


class SqliteStore(Store):
    def __init__(self, tenant: str, root: Path):
        from plexus.crucible.backends.sqlite import SqliteBackend

        self.b = SqliteBackend(tenant, root)
        self.path = Path(self.b.path) if hasattr(self.b, "path") else None

    def status(self, tid: str) -> dict[str, Any] | None:
        return self.b.task_status(tid)

    def dump(self) -> dict[str, Any]:
        db = self.path if self.path and self.path.suffix == ".db" else next(Path(self.b.root).rglob("*.db"))  # type: ignore[attr-defined]
        c = sqlite3.connect(str(db))
        c.row_factory = sqlite3.Row

        def rows(sql: str) -> list[dict[str, Any]]:
            return [dict(r) for r in c.execute(sql).fetchall()]

        facts = rows(
            "SELECT id, entity_name AS subject, predicate, value, status, valid_from, valid_to, recorded_at FROM facts"
        )
        df = {}
        for r in rows("SELECT decision_id, fact_id FROM decision_facts"):
            df.setdefault(r["decision_id"], []).append(r["fact_id"])
        decisions = [
            {**d, "based_on": df.get(d["id"], [])} for d in rows("SELECT id, text, at FROM decisions")
        ]
        hi = {}
        for r in rows("SELECT handoff_id, kind, item_id FROM handoff_items"):
            if r["kind"] in ("fact", "Fact"):
                hi.setdefault(r["handoff_id"], []).append(r["item_id"])
        handoffs = [{**h, "fact_ids": hi.get(h["id"], [])} for h in rows("SELECT id, note FROM handoffs")]
        wrote = [
            {"node": r["node_id"], "agent": r["agent_id"], "at": r["at"]}
            for r in rows(
                "SELECT w.node_id, s.agent_id, s.at FROM step_wrote w JOIN steps s ON s.id = w.step_id"
            )
        ]
        reads = [
            {"agent": r["agent_id"], "at": r["at"], "fact": r["fact_id"], "value": r["value"]}
            for r in rows(
                "SELECT s.agent_id, s.at, r.fact_id, f.value FROM step_reads r JOIN steps s ON s.id = r.step_id "
                "LEFT JOIN facts f ON f.id = r.fact_id"
            )
        ]
        tasks = rows("SELECT id, status, claimed_by, version FROM tasks")
        links = rows("SELECT src, dst, kind FROM fact_links")
        c.close()
        return {"facts": facts, "decisions": decisions, "handoffs": handoffs, "wrote": wrote, "reads": reads,
                "changes": [], "tasks": tasks, "fact_links": links}  # fmt: skip

    def close(self) -> None:
        self.b.close()


class FileStore(Store):
    """B0': a task is done when its required artifact file exists (§5.3: harness-mediated progression)."""

    def __init__(self, workdir: Path):
        self.w = workdir
        self.created: set[str] = {t.id for t in S.INITIAL_TASKS}
        self.interrupted: set[str] = set()  # killed mid-task: not done until a reclaim turn has run (§5.3)

    def status(self, tid: str) -> dict[str, Any] | None:
        if tid not in self.created:
            return None
        p = self.w / S.TASK_BY_ID[tid].artifact_path
        if tid not in self.interrupted and p.exists() and p.stat().st_size > 0:
            return {"id": tid, "status": "done", "claimed_by": "", "lease_until": 0}
        return {"id": tid, "status": "open", "claimed_by": "", "lease_until": 0}

    def dump(self) -> dict[str, Any]:
        mem = {}
        for p in sorted((self.w / "memory").rglob("*")):
            if p.is_file():
                mem[p.relative_to(self.w).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
        return {"memory_files": mem}


# ------------------------------------------------------------------------------------------------ the driver
@dataclass
class L8State:
    arm: str
    schedule: dict[str, Any]
    store: Store
    turn_no: int = 0
    step: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    fired: dict[str, int] = field(default_factory=dict)
    landed: list[dict[str, Any]] = field(default_factory=list)
    started: float = field(default_factory=time.time)
    holds: dict[str, str] = field(
        default_factory=dict
    )  # agent -> task (MCP: after claim result; B0': assignment)
    calls_since_claim: dict[str, int] = field(default_factory=dict)
    k2_wrote: bool = False

    def event(self, name: str, **info: Any) -> dict[str, Any]:
        ev = {"event": name, "turn": self.turn_no, "step": self.step, "t_ms": int(time.time() * 1000), **info}
        self.events.append(ev)
        return ev


@dataclass
class L8Turn:
    kind: str  # init | task | special
    agent: str
    name: str
    reclaim_from: str = ""
    attempt: int = 1


def _role_files(role: str) -> str:
    t = S.role_text(role)
    return (
        t.replace("register a source (`add_source`), then assert only what it actually says, linked to that source",
                  "note the source, then record only what it actually says, with that source")
        .replace("(recall first)", "(read the team memory first)")
        .replace("you recall the facts", "you read the facts")
        .replace("the artifact ids and the fact ids", "the artifact paths and the facts")
    )  # fmt: skip


class L8Driver(ClaudeDriver):
    """``ClaudeDriver`` with the L8 tool surface, prompts and kill points."""

    def __init__(self, cfg: ClaudeConfig, st: L8State, sentinels: dict[str, Any], on_event: Any = None):
        super().__init__(cfg, on_event)
        self.st = st
        self.mcp = st.arm != "B0p"
        self.artifact_ids: dict[str, str] = {}
        self.turn_meta: list[dict[str, Any]] = []
        x2 = st.schedule["x2_old_token"]
        self.extra_docs = {"s03_ratelimit_note": S.s03_note(x2)}

    # -- command -------------------------------------------------------------------------------------------
    def command(self, prompt: str, system: str) -> list[str]:
        cfg = self.cfg
        allowed = f"{MCP_PREFIX}*,{FILE_TOOLS}" if self.mcp else FILE_TOOLS
        return [
            *(cfg.launcher or [cfg.binary()]), "-p", prompt, "--model", cfg.model, "--max-turns", str(cfg.max_turns),
            "--mcp-config", str(cfg.mcp_config), "--strict-mcp-config", "--allowedTools", allowed,
            "--tools", FILE_TOOLS, "--output-format", "stream-json", "--verbose", "--no-session-persistence",
            "--append-system-prompt", system,
        ]  # fmt: skip

    # -- prompts -------------------------------------------------------------------------------------------
    def step_hint(self) -> str:
        n = self.st.step + 1
        return (
            f"\nStep numbers: pass `step` on every Plexus call: step={n} on your first call in this assignment, "
            f"step={n + 1} on the next, then {n + 2}, {n + 3}, ... (one number per call, including start_session; "
            "never reuse or skip a number)."
        )

    def prompt(self, t: L8Turn) -> str:
        if t.kind == "init":
            tasks = json.dumps([x.spec() for x in S.INITIAL_TASKS], indent=1)
            if self.mcp:
                return (
                    "ASSIGNMENT (project kickoff). Your agent_id is 'planner'. Call start_session, then call create_tasks "
                    f"ONCE with EXACTLY this task list (same ids, titles, priorities and dependencies, do not change "
                    f"anything):\n{tasks}\nThen stop.{self.step_hint()}"
                )
            return (
                "ASSIGNMENT (project kickoff). Your agent_id is 'planner'. Write the sprint's task list to "
                f"`memory/tasks.md` with EXACTLY these tasks (same ids, titles, priorities and dependencies):\n{tasks}\n"
                "Then stop."
            )
        if t.kind == "special":
            sp = S.SPECIALS[t.name]
            body = sp.mcp if self.mcp else sp.files
            docs = S.docs_block(sp.docs)
            if self.mcp:
                return (
                    f"ASSIGNMENT (event: {t.name}). Your agent_id is '{t.agent}' and your role is {t.agent}. This is not "
                    f"a claimed task: do NOT call claim_next_task. Steps: start_session, then:\n{body}{docs}"
                    f"{self.ids_block()}\n\nThen stop.{self.step_hint()}"
                )
            return f"ASSIGNMENT (event: {t.name}). Your agent_id is '{t.agent}' and your role is {t.agent}.\n{body}{docs}\n\nThen stop."
        task = S.TASK_BY_ID[t.name]
        docs = S.docs_block(task.docs, {k: v for k, v in self.extra_docs.items() if k in task.extra_docs})
        if self.mcp:
            lease = REAL_BUILDER_LEASE_MS if t.agent == "builder" else REAL_LEASE_MS
            took = (
                f"\nThis task was abandoned by '{t.reclaim_from}' (its lease expired). Your claim_next_task result will "
                f"show reclaimed_from='{t.reclaim_from}'. Write ONE remember_episode saying you took the task over, then "
                "do the task as described."
            ) if t.reclaim_from else ""  # fmt: skip
            return (
                f"ASSIGNMENT. Your agent_id is '{t.agent}' and your role is {t.agent}. Do exactly ONE task.\n"
                f"Task id: {task.id}\nTask title: {task.title}\n"
                f"Steps: start_session; claim_next_task with lease_ms={lease} (it must return task '{task.id}'); "
                f"then:\n{task.mcp}{took}{docs}{self.ids_block()}\n\nStop after complete_task (and the handoff, if "
                f"asked).{self.step_hint()}"
            )
        took = (
            f"\n'{t.reclaim_from}' was interrupted while on {task.id}; check `memory/` and `artifacts/` and finish it."
            if t.reclaim_from else ""
        )  # fmt: skip
        deps = ", ".join(task.depends_on) or "none"
        return (
            f"ASSIGNMENT. Your agent_id is '{t.agent}' and your role is {t.agent}. The lead assigns you exactly ONE task.\n"
            f"Task id: {task.id}\nTask title: {task.title}\nDepends on (done): {deps}\n"
            f"Do this:\n{task.files}{took}{docs}\n\nStop when the artifact is written and the task is recorded as done."
        )

    def ids_block(self) -> str:
        if not self.artifact_ids:
            return ""
        lines = [f"- artifact of {tid}: artifact_id {aid}" for tid, aid in self.artifact_ids.items()]
        return "\n\nIds from earlier work:\n" + "\n".join(lines)

    def system(self, agent: str) -> str:
        if self.mcp:
            return S.common_mcp() + "\n" + S.role_text(agent)
        return _role_files(agent)

    # -- one turn ------------------------------------------------------------------------------------------
    async def play(self, t: L8Turn) -> TurnReport:
        st = self.st
        st.turn_no += 1
        rep = TurnReport(st.turn_no, t.agent, t.name, t.kind)
        self.reports.append(rep)
        self.cur = t
        self.wrote_this_turn = False
        self.calls_this_turn = 0
        st.holds.pop(t.agent, None)
        st.calls_since_claim.pop(t.agent, None)
        if t.kind == "task" and not self.mcp:
            st.holds[t.agent] = t.name
            st.calls_since_claim[t.agent] = 0
        meta = {"turn": st.turn_no, "agent": t.agent, "name": t.name, "kind": t.kind, "reclaim_from": t.reclaim_from,
                "attempt": t.attempt, "start_ms": int(time.time() * 1000)}  # fmt: skip
        self.turn_meta.append(meta)
        prompt = self.prompt(t)
        try:
            await self._run_process(None, t, rep, self.command(prompt, self.system(t.agent)))  # type: ignore[arg-type]
        finally:
            meta["end_ms"] = int(time.time() * 1000)
            meta["killed"] = rep.killed
            meta["prompt_chars"] = len(prompt)
            self._flush_transcript(rep)
        return rep

    def _on_stream_event(self, w, turn, rep, ev, pending, proc) -> None:  # noqa: ANN001
        kind = ev.get("type")
        st = self.st
        if kind == "system" and ev.get("subtype") == "init":
            self.turn_meta[-1]["model"] = ev.get("model")
            self.turn_meta[-1]["claude_code_version"] = ev.get("claude_code_version")
            if self.mcp:
                srv = [s for s in ev.get("mcp_servers", []) if s.get("name") == "plexus"]
                if not srv or srv[0].get("status") != "connected":
                    raise ClaudeRunError(f"Plexus MCP server did not connect: {ev.get('mcp_servers')}")
        elif kind == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                name = block.get("name", "")
                pending[block["id"]] = (name, block.get("input") or {})
                self.calls_this_turn += 1
                if name.startswith(MCP_PREFIX):
                    st.step += 1
                    rep.plexus_calls += 1
                    self._emit(f"step {st.step:>3}  {turn.agent:<10} {name[len(MCP_PREFIX) :]}")
                else:
                    self._emit(
                        f"  file   {turn.agent:<10} {name} {str((block.get('input') or {}).get('file_path', ''))[-60:]}"
                    )
        elif kind == "user":
            for block in ev.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    self._on_result(turn, rep, block, pending)
        elif kind == "result":
            rep.result = ev
            denials = ev.get("permission_denials") or []
            if denials:
                rep.problems.append(f"permission_denials: {json.dumps(denials)[:600]}")
            if ev.get("is_error") or ev.get("subtype") != "success":
                rep.problems.append(f"result subtype={ev.get('subtype')} is_error={ev.get('is_error')}")

    def _on_result(self, t: L8Turn, rep: TurnReport, block: dict[str, Any], pending: dict[str, Any]) -> None:
        st = self.st
        name, args = pending.pop(block.get("tool_use_id"), ("", {}))
        if block.get("is_error"):
            rep.problems.append(f"{name} failed: {str(block.get('content'))[:200]}")
            return
        short = name[len(MCP_PREFIX) :] if name.startswith(MCP_PREFIX) else name
        data = _result_json(block.get("content")) if name.startswith(MCP_PREFIX) else {}
        if short == "claim_next_task" and data.get("task"):
            st.holds[t.agent] = data["task"]["id"]
            st.calls_since_claim[t.agent] = 0
        elif t.agent in st.holds:
            st.calls_since_claim[t.agent] = st.calls_since_claim.get(t.agent, 0) + 1
        if short == "complete_task":
            tid = str(args.get("task_id") or st.holds.get(t.agent, ""))
            if data.get("artifact_ids") and tid:
                self.artifact_ids[tid] = data["artifact_ids"][0]
            st.holds.pop(t.agent, None)
        is_write = (short in MCP_WRITES) if self.mcp else (short in ("Write", "Edit"))
        is_art_write = short == "Write" and "artifacts" in str(args.get("file_path", "")).replace("\\", "/")
        self._maybe_kill(t, is_write, is_art_write)

    def _maybe_kill(self, t: L8Turn, is_write: bool, is_art_write: bool) -> None:
        st, k = self.st, self.st.schedule["kills"]
        if t.kind != "task":
            return
        why = ""
        if (
            t.agent == "builder"
            and "K1" not in st.fired
            and st.turn_no >= k["K1"]["from_turn"]
            and t.agent in st.holds
            and st.calls_since_claim.get(t.agent, 0) >= 1
        ):
            why = "K1"
        elif (
            t.agent == "researcher"
            and "K2" not in st.fired
            and st.turn_no >= k["K2"]["from_turn"]
            and t.name in k["K2"]["tasks"]
            and is_art_write
        ):
            why = "K2"
        elif (
            t.agent == "planner" and "K3" not in st.fired and st.turn_no >= k["K3"]["from_turn"] and is_write
        ):
            why = "K3"  # fmt: skip
        if not why:
            return
        st.fired[why] = st.turn_no
        task = st.holds.get(t.agent, t.name)
        st.event("kill", kill=why, agent=t.agent, task=task, holds=t.agent in st.holds)
        raise AgentKilled(t.agent, task)


# ------------------------------------------------------------------------------------------------ the scheduler
async def run_schedule(st: L8State, driver: L8Driver, workdir: Path, on_commit: Any, log: Any) -> str:
    sched = st.schedule
    commits = [Edit.from_json(c) for c in sched["commits"]]
    mods = initial_modules(sched["initial_tokens"])
    pending_specials: list[L8Turn] = []
    attempts: dict[str, int] = {}
    reclaim: dict[str, str] = {}  # B0': task -> killed agent
    v2_fired = False
    mcp = st.arm != "B0p"
    created = {t.id for t in S.INITIAL_TASKS}

    async def play(turn: L8Turn) -> bool:
        """Run one turn; True if the agent was killed."""
        try:
            await driver.play(turn)
        except AgentKilled as k:
            log(f"  killed {k.agent} on {k.task_id}")
            if mcp:
                stt = st.store.status(k.task_id)
                if stt and stt.get("status") == "claimed":
                    delay = (int(stt["lease_until"]) + 100) / 1000 - time.time()
                    st.event("lease_wait", task=k.task_id, wait_s=round(max(delay, 0), 1))
                    if delay > 0:
                        await asyncio.sleep(delay)
            else:
                await asyncio.sleep(B0P_LEASE_WAIT_S)
                if turn.kind == "task" and isinstance(st.store, FileStore):
                    st.store.interrupted.add(turn.name)  # the lead knows the agent was interrupted: reassign
                    reclaim[turn.name] = turn.agent
            st.holds.pop(k.agent, None)
            return True
        return False

    def boundary() -> None:
        nonlocal v2_fired
        nxt = st.turn_no + 1
        for e in commits:
            if e.turn <= nxt and not any(x["k"] == e.k for x in st.landed):
                before = on_commit("before")
                sha = land(workdir / "repo", mods, e)
                after = on_commit("after")
                rec = {"k": e.k, "kind": e.kind, "funcs": e.funcs, "sched_turn": e.turn, "landed_before_turn": nxt,
                       "sha": sha, "t_ms": int(time.time() * 1000), "hook": {"changes_before": before, "changes_after": after}}  # fmt: skip
                st.landed.append(rec)
                st.event("commit", k=e.k, kind=e.kind, funcs=e.funcs, sha=sha[:10])
                log(f"  commit {e.k} ({e.kind} {e.funcs}) before turn {nxt}")
        if not v2_fired and nxt >= sched["v2_turn"]:
            v2_fired = True
            st.event("publish_v2")
            pending_specials.extend(
                [L8Turn("special", "researcher", "ingest-v2"), L8Turn("special", "planner", "adopt-v2")]
            )

    await play(L8Turn("init", "planner", "init"))
    if mcp:
        missing = [t.id for t in S.INITIAL_TASKS if st.store.status(t.id) is None]
        if missing:
            raise ClaudeRunError(f"the planner did not create these tasks: {missing}")
    while True:
        if st.turn_no >= MAX_PROCESSES:
            return f"stopped: {MAX_PROCESSES} processes"
        boundary()
        if pending_specials:
            sp = pending_specials.pop(0)
            await play(sp)
            if sp.name == "adopt-v2":
                created.add("t12-update-endpoints-for-v2")
                if isinstance(st.store, FileStore):
                    st.store.created.add("t12-update-endpoints-for-v2")
            continue
        statuses = {tid: st.store.status(tid) for tid in S.TASK_BY_ID if tid in created or mcp}
        done = {tid for tid, s in statuses.items() if s and s.get("status") == "done"}
        now = int(time.time() * 1000)
        ready = []
        for t in S.TASKS:
            s = statuses.get(t.id)
            if not s or t.id in done or not all(d in done for d in t.depends_on):
                continue
            if s["status"] == "open" or (s["status"] == "claimed" and int(s.get("lease_until") or 0) < now):
                ready.append((t, s))
        if not ready:
            live = [s for s in statuses.values() if s and s["status"] == "claimed"]
            if live:
                delay = (min(int(s["lease_until"]) for s in live) + 100) / 1000 - time.time()
                await asyncio.sleep(max(delay, 0.5))
                continue
            if all((statuses.get(t.id) or {}).get("status") == "done" for t in S.TASKS):
                return "completed"
            return "stuck: " + ",".join(
                t.id for t in S.TASKS if (statuses.get(t.id) or {}).get("status") != "done"
            )
        ready.sort(key=lambda x: (-x[0].priority, S.TASKS.index(x[0])))
        task, s = ready[0]
        attempts[task.id] = attempts.get(task.id, 0) + 1
        if attempts[task.id] > MAX_ATTEMPTS:
            return f"gave up: {task.id} not done after {MAX_ATTEMPTS} attempts"
        prev = (
            str(s.get("claimed_by") or "") if (mcp and s["status"] == "claimed") else reclaim.pop(task.id, "")
        )
        if not mcp and isinstance(st.store, FileStore):
            st.store.interrupted.discard(task.id)
        agent = ("planner" if prev == "researcher" else "researcher") if prev else task.role
        if prev:
            st.event("reclaim", task=task.id, agent=agent, reclaimed_from=prev)
        await play(L8Turn("task", agent, task.id, reclaim_from=prev or "", attempt=attempts[task.id]))


# ------------------------------------------------------------------------------------------------ arms
@dataclass
class HookServer:
    host: str
    port: int
    proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{HOOK_PORT}"

    def start(self, log_path: Path) -> None:
        env = {**os.environ, "FALKORDB_HOST": self.host, "FALKORDB_PORT": str(self.port), "PLEXUS_EMBEDDER": "hash",
               "PLEXUS_AUDIT_MODE": "full"}  # fmt: skip
        self.log = open(log_path, "ab")  # noqa: SIM115
        self.proc = subprocess.Popen(
            [plexus_mcp_command(), "--transport", "http", "--port", str(HOOK_PORT)],
            env=env, stdout=self.log, stderr=subprocess.STDOUT,
        )  # fmt: skip
        import socket

        for _ in range(120):
            with socket.socket() as s:
                if s.connect_ex(("127.0.0.1", HOOK_PORT)) == 0:
                    return
            time.sleep(0.5)
        raise RuntimeError("the hook MCP server did not start")

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.log.close()


def copy_history_b0(dest: Path, tenant: str, scratch: Path) -> int:
    """Play the 20 sprints into a FilesBackend (B0) and copy its files to ``dest`` (B0' reads them as markdown)."""
    from plexus.crucible.api import BackendSpec
    from plexus.crucible.backends import open_backend
    from plexus.crucible.l2.scale_scenario import play_scale

    root = scratch / "b0hist"
    b = open_backend(BackendSpec(arm="B0", tenant=tenant, root=str(root)))
    play_scale(b, 20)
    b.close()
    src = next(p for p in root.rglob("MEMORY.md")).parent
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns("*.lock"))
    return sum(p.stat().st_size for p in dest.rglob("*") if p.is_file())


def run_arm(
    arm: str, seed: int, out: Path, *, host: str = "127.0.0.1", port: int = 6365, model: str = "sonnet",
    max_turns: int = 25, launcher: list[str] | None = None, scratch: Path | None = None, log: Any = print,
    hook: HookServer | None = None, tag: str = "",
) -> dict[str, Any]:  # fmt: skip
    """One arm x one seed. Writes ``out/runs/<seed>/<arm>/``: run.json, transcripts/, store_dump.json, final
    artifacts / memory, the repo's git log. Returns run.json's content."""
    sched, sentinels = load_seed(out, seed)
    run_dir = out / "runs" / str(seed) / arm
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    scratch = Path(scratch or os.environ.get("TMPDIR") or "/tmp")
    work_root = Path(__import__("tempfile").mkdtemp(prefix=f"l8-{seed}-{arm}-", dir=str(scratch)))
    workdir = work_root / "work"
    (workdir / "artifacts").mkdir(parents=True)
    tenant = f"l8_{arm.lower()}_{seed}_{time.strftime('%H%M%S')}{tag}"
    git0 = git_state()
    t0 = time.time()
    log(f"== L8 seed {seed} arm {arm}: workdir {workdir}")
    # history (the 20 sprints) into the arm's store, then the repo
    hist_t = time.time()
    store: Store
    cfgfile = work_root / "mcp.json"
    if arm == "P":
        from plexus.crucible.api import BackendSpec
        from plexus.crucible.backends import open_backend
        from plexus.crucible.l2.scale_scenario import play_scale
        from plexus.graph.client import GraphClient
        from plexus.graph.schema import apply_schema
        from plexus.graph.tenancy import graph_name

        gc = GraphClient(host=host, port=port)
        apply_schema(gc, graph_name(tenant))
        gc.close()
        b = open_backend(
            BackendSpec(arm="P-mcp", tenant=tenant, root="", host=host, port=port, embedder="hash")
        )
        play_scale(b, 20)
        b.close()
        env = {
            "FALKORDB_HOST": host,
            "FALKORDB_PORT": str(port),
            "PLEXUS_EMBEDDER": "hash",
            "PLEXUS_AUDIT_MODE": "full",
        }
        cfg_json = {"mcpServers": {"plexus": {"command": plexus_mcp_command(),
                    "args": ["--transport", "stdio", "--tenant", tenant], "env": env}}}  # fmt: skip
        store = PlexusStore(tenant, host, port)
    elif arm == "B1":
        from plexus.crucible.api import BackendSpec
        from plexus.crucible.backends import open_backend
        from plexus.crucible.l2.scale_scenario import play_scale

        root = work_root / "store"
        b = open_backend(BackendSpec(arm="B1", tenant=tenant, root=str(root)))
        play_scale(b, 20)
        b.close()
        cfg_json = {"mcpServers": {"plexus": {"command": sys.executable, "args": [
            "-m", "plexus.crucible.l3.baseline_mcp", "--arm", "B1", "--root", str(root), "--tenant", tenant,
            "--embedder", "hash"], "env": {}}}}  # fmt: skip
        store = SqliteStore(tenant, root)
    elif arm == "B0p":
        hist_bytes = copy_history_b0(workdir / "history", tenant, work_root)
        (workdir / "memory").mkdir()
        (workdir / "CLAUDE.md").write_text(S.CLAUDE_MD, encoding="utf-8", newline="\n")
        cfg_json = {"mcpServers": {}}
        store = FileStore(workdir)
        log(f"  history/ {hist_bytes:,} bytes")
    else:
        raise ValueError(arm)
    cfgfile.write_text(json.dumps(cfg_json, indent=2), encoding="utf-8")
    hist_s = round(time.time() - hist_t, 1)
    mods = initial_modules(sched["initial_tokens"])
    init_sha = init_repo(workdir / "repo", mods)
    hook_info: dict[str, Any] = {"installed": False}
    if arm == "P":
        assert hook is not None, "arm P needs the hook MCP server"
        subprocess.run(
            [sys.executable, "-m", "plexus.codescan", "hook-git", "--repo", str(workdir / "repo"), "--tenant", tenant,
             "--url", hook.url], check=True, capture_output=True, text=True,
        )  # fmt: skip
        base = subprocess.run(
            [sys.executable, "-m", "plexus.codescan", "baseline", "--repo", str(workdir / "repo"), "--tenant", tenant,
             "--url", hook.url, "--paths", *[f"{m}.py" for m in mods]], capture_output=True, text=True,
            env={**os.environ, "FALKORDB_HOST": host, "FALKORDB_PORT": str(port)},
        )  # fmt: skip
        hook_info = {
            "installed": True,
            "url": hook.url,
            "baseline": (base.stdout + base.stderr).strip()[-400:],
        }

    def on_commit(phase: str) -> int | None:
        return store.count_changes() if isinstance(store, PlexusStore) else None

    st = L8State(arm, sched, store)
    cfg = ClaudeConfig(
        workdir=workdir, mcp_config=cfgfile, model=model, max_turns=max_turns, launcher=launcher
    )
    driver = L8Driver(cfg, st, sentinels, on_event=log)
    status, error = "completed", ""
    try:
        status = asyncio.run(run_schedule(st, driver, workdir, on_commit, log))
    except Exception as exc:  # noqa: BLE001 - recorded, then scored as far as it got
        status, error = "aborted", f"{type(exc).__name__}: {exc}"[:500]
    # outputs
    summ = driver.summary(None)  # type: ignore[arg-type]
    (run_dir / "transcripts").mkdir()
    for name, text in driver.transcripts().items():
        (run_dir / "transcripts" / name).write_text(text, encoding="utf-8", newline="\n")
    dump = store.dump()
    (run_dir / "store_dump.json").write_text(json.dumps(dump, indent=0, default=str) + "\n", encoding="utf-8")
    shutil.copytree(workdir / "artifacts", run_dir / "artifacts")
    if (workdir / "memory").exists():
        shutil.copytree(workdir / "memory", run_dir / "memory")
    (run_dir / "repo_log.txt").write_text(git(workdir / "repo", "log", "--format=%H %s"), encoding="utf-8")
    hook_failed = [c["k"] for c in st.landed if arm == "P" and not (
        (c["hook"]["changes_after"] or 0) > (c["hook"]["changes_before"] or 0))]  # fmt: skip
    rec = {
        "kind": "crucible-l8-run", "prompt_version": S.PROMPT_VERSION, "seed": seed, "arm": arm, "tenant": tenant,
        "status": status, "error": error, "git": git0, "claude_version": claude_version() if not launcher else "launcher",
        "model_alias": model, "max_turns": max_turns, "history_seconds": hist_s, "initial_sha": init_sha,
        "turns": driver.turn_meta, "events": st.events, "commits_landed": st.landed,
        "commits_not_landed": [c["k"] for c in sched["commits"] if not any(x["k"] == c["k"] for x in st.landed)],
        "kills_fired": st.fired, "hook": hook_info, "hook_failed_commits": hook_failed,
        "claude": {k: v for k, v in summ.items() if k != "per_turn"}, "per_turn": summ["per_turn"],
        "wall_s": round(time.time() - t0, 1), "workdir": str(workdir).replace("\\", "/"),
        "all_tokens_count": len(all_tokens(sentinels, sched)),
    }  # fmt: skip
    (run_dir / "run.json").write_text(
        json.dumps(rec, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    store.close()
    log(
        f"== {arm} seed {seed}: {status} {error} turns={st.turn_no} cost=${summ['total_cost_usd']} wall={rec['wall_s']}s"
    )
    return rec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l8")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--out", type=Path, default=OUT_DEFAULT)
    r = sub.add_parser("arm")
    r.add_argument("--seed", type=int, required=True)
    r.add_argument("--arm", choices=ARMS, required=True)
    r.add_argument("--out", type=Path, default=OUT_DEFAULT)
    r.add_argument("--port", type=int, default=6365)
    r.add_argument("--model", default="sonnet")
    r.add_argument("--scratch", type=Path, default=None)
    r.add_argument("--launcher", default=None, help="tests: a stand-in for claude (space-separated argv)")
    a = ap.parse_args(argv)
    if a.cmd == "prepare":
        prepare(a.out)
        print(f"prepared {len(SEEDS)} seeds under {a.out}")
        return 0
    hook = None
    if a.arm == "P":
        hook = HookServer("127.0.0.1", a.port)
        (a.out / "logs").mkdir(parents=True, exist_ok=True)
        hook.start(a.out / "logs" / f"hook-{a.seed}.log")
    try:
        rec = run_arm(a.arm, a.seed, a.out, port=a.port, model=a.model, scratch=a.scratch, hook=hook,
                      launcher=a.launcher.split() if a.launcher else None,
                      log=lambda s: print(s, flush=True))  # fmt: skip
    finally:
        if hook:
            hook.stop()
    return 0 if rec["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
