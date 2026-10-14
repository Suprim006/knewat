"""Run the Acme Notes scenario with three REAL Claude Code agents (``claude -p``) against Plexus over MCP.

Each turn is one headless ``claude -p`` process for one role, started by the shared scheduler
(``plexus.demo.engine``): the planner creates the task graph and makes decisions, the researcher turns documents into
sourced facts, the builder claims build tasks and hands off. Every process gets a generated per-run ``mcp.json``
(stdio ``plexus-mcp --tenant <run tenant>``), ``--strict-mcp-config``, no built-in tools and only
``mcp__plexus__*`` allowed, and runs without ``ANTHROPIC_API_KEY`` so usage goes to the signed-in subscription.

The orchestrator reads each process's ``stream-json`` output: it counts Plexus tool calls on the global step counter,
tracks the claim / complete state, applies the fault script (killing the builder process mid-task) and checks every
``result`` for ``is_error`` and ``permission_denials`` (a blocked tool still exits 0). Plexus itself contains no LLM.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plexus.demo.engine import BUILDER, AgentKilled, Turn, World
from plexus.demo.engine import run as run_engine
from plexus.demo.scenario import (
    FaultScript,
    TaskDef,
    load_scenario,
    role_prompt,
)

MCP_PREFIX = "mcp__plexus__"
REAL_LEASE_MS = 60_000  # ordinary leases in real runs (a turn is slow)
REAL_BUILDER_LEASE_MS = 45_000
TURN_TIMEOUT_S = 900


class ClaudeRunError(RuntimeError):
    """A real Claude turn failed (error result, permission denial, MCP not connected, task not completed...)."""


class StopRun(Exception):
    """``--stop-after-turns`` reached (a pilot): not an error."""


# ------------------------------------------------------------------------------------------------ command line
def clean_env(base: dict[str, str] | None = None, extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment for ``claude``: no API key (subscription billing), nothing else changed."""
    env = dict(os.environ if base is None else base)
    env.pop("ANTHROPIC_API_KEY", None)
    env.update(extra or {})
    return env


def plexus_mcp_command() -> str:
    """The ``plexus-mcp`` script of the running environment (no ``uv run``: it starts faster)."""
    exe = "plexus-mcp.exe" if os.name == "nt" else "plexus-mcp"
    p = Path(sys.executable).parent / exe
    return str(p) if p.exists() else exe


def build_mcp_config(
    tenant: str, mcp_command: str | None = None, env: dict[str, str] | None = None
) -> dict[str, object]:
    """The MCP config of one stdio Plexus server bound to ``tenant`` (what ``claude --mcp-config`` reads)."""
    server_env = {
        "FALKORDB_HOST": os.environ.get("FALKORDB_HOST", "127.0.0.1"),
        "FALKORDB_PORT": os.environ.get("FALKORDB_PORT", "6379"),
    }
    if os.environ.get("PLEXUS_EMBEDDER"):
        server_env["PLEXUS_EMBEDDER"] = os.environ["PLEXUS_EMBEDDER"]
    server_env.update(env or {})
    return {
        "mcpServers": {
            "plexus": {
                "command": mcp_command or plexus_mcp_command(),
                "args": ["--transport", "stdio", "--tenant", tenant],
                "env": server_env,
            }
        }
    }


def build_http_mcp_config(url: str, tenant: str) -> dict[str, object]:
    """The MCP config of a streamable-HTTP Plexus endpoint; the tenant is pinned by the URL path ``/mcp/t/<tenant>``."""
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"--http must be an http(s) URL, got {url!r}")
    base = url.rstrip("/")
    if base.endswith("/mcp"):
        base += f"/t/{tenant}"
    elif "/mcp/t/" not in base:
        base += f"/mcp/t/{tenant}"
    return {"mcpServers": {"plexus": {"type": "http", "url": base}}}


def write_mcp_config(
    path: Path, tenant: str, mcp_command: str | None = None, env: dict[str, str] | None = None
) -> Path:
    """The per-run ``mcp.json``: one stdio Plexus server bound to ``tenant``."""
    path.write_text(json.dumps(build_mcp_config(tenant, mcp_command, env), indent=2), encoding="utf-8")
    return path


@dataclass
class ClaudeConfig:
    workdir: Path
    mcp_config: Path
    model: str = "sonnet"
    max_turns: int = 25
    claude_bin: str = ""
    launcher: list[str] | None = None  # tests: a stand-in for the claude executable
    turn_timeout_s: int = TURN_TIMEOUT_S
    stop_after_turns: int | None = None

    def binary(self) -> str:
        return self.claude_bin or shutil.which("claude") or "claude"


def build_command(cfg: ClaudeConfig, prompt: str, system_append: str) -> list[str]:
    """The exact ``claude`` argv for one turn (see docs/demo.md)."""
    return [
        *(cfg.launcher or [cfg.binary()]),
        "-p",
        prompt,
        "--model",
        cfg.model,
        "--max-turns",
        str(cfg.max_turns),
        "--mcp-config",
        str(cfg.mcp_config),
        "--strict-mcp-config",
        "--allowedTools",
        "mcp__plexus__*",
        "--tools",
        "",
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        "--append-system-prompt",
        system_append,
    ]


# ------------------------------------------------------------------------------------------------ prompts
def _documents(w: World, stems: tuple[str, ...]) -> str:
    if not stems:
        return ""
    parts = []
    for stem in stems:
        d = w.scenario.sources[stem]
        parts.append(
            f"=== DOCUMENT: {d.uri} (kind {d.kind}, trust {d.trust}) ===\n{d.text}\n=== END DOCUMENT ==="
        )
    return "\n\nDocuments for this assignment:\n\n" + "\n\n".join(parts)


@dataclass
class TeamState:
    """Ids the harness learned from the tool results so far; shown to later turns so they can cite them."""

    facts: dict[str, tuple[str, str]] = field(default_factory=dict)  # fact_id -> (predicate, value)
    artifacts: dict[str, str] = field(default_factory=dict)  # task id -> artifact id
    sources: dict[str, str] = field(default_factory=dict)  # uri -> source_id

    def render(self) -> str:
        lines = []
        for fid, (pred, val) in self.facts.items():
            lines.append(f"- fact {pred} = {val!r}: fact_id {fid}")
        for tid, aid in self.artifacts.items():
            lines.append(f"- artifact of {tid}: artifact_id {aid}")
        for uri, sid in self.sources.items():
            lines.append(f"- source {uri}: source_id {sid}")
        if not lines:
            return ""
        return "\n\nIds from earlier work (current facts only; use them instead of guessing):\n" + "\n".join(
            lines
        )

    def absorb(self, name: str, args: dict[str, Any], data: dict[str, Any], task_id: str = "") -> None:
        if name == "assert_fact" and data.get("fact_id"):
            for old in data.get("superseded") or []:
                self.facts.pop(old, None)
            self.facts[data["fact_id"]] = (str(args.get("predicate", "")), str(args.get("value", "")))
        elif name == "add_source" and data.get("source_id"):
            self.sources[str(data.get("uri") or args.get("uri"))] = data["source_id"]
        elif name == "complete_task" and data.get("artifact_ids") and task_id:
            self.artifacts[task_id] = data["artifact_ids"][0]


def step_hint(w: World) -> str:
    n = w.step + 1
    return (
        f"\nStep numbers: pass `step` on every Plexus call: step={n} on your first call in this assignment, "
        f"step={n + 1} on the next, then {n + 2}, {n + 3}, ... (one number per call, including start_session; "
        "never reuse or skip a number)."
    )


def init_prompt(w: World) -> str:
    tasks = json.dumps([t.spec() for t in w.scenario.tasks], indent=1)
    return (
        "ASSIGNMENT (project kickoff). Your agent_id is 'planner'. Call start_session, then call create_tasks ONCE with "
        "EXACTLY this task list (same ids, titles, priorities and dependencies, do not change anything):\n"
        f"{tasks}\nThen stop.{step_hint(w)}"
    )


def task_prompt(w: World, turn: Turn, state: TeamState, lease_ms: int) -> str:
    task: TaskDef = turn.task  # type: ignore[assignment]
    took_over = ""
    if turn.reclaim_from:
        took_over = (
            f"\nThis task was abandoned by '{turn.reclaim_from}' (its lease expired). Your claim_next_task result will "
            f"show reclaimed_from='{turn.reclaim_from}'. Write ONE remember_episode saying you took the task over, then "
            "do the task as described."
        )
    return (
        f"ASSIGNMENT. Your agent_id is '{turn.agent}' and your role is {turn.agent}. Do exactly ONE task.\n"
        f"Task id: {task.id}\nTask title: {task.title}\n"
        f"Steps: start_session; claim_next_task with lease_ms={lease_ms} (it must return task '{task.id}'); "
        f"then:\n{task.brief}{took_over}"
        f"{_documents(w, task.sources)}{state.render()}\n\nStop after complete_task (and the handoff, if asked).{step_hint(w)}"
    )


def special_prompt(w: World, turn: Turn, state: TeamState) -> str:
    sp = w.scenario.specials[turn.name]
    return (
        f"ASSIGNMENT (event: {turn.name}). Your agent_id is '{turn.agent}' and your role is {turn.agent}. "
        f"This is not a claimed task: do NOT call claim_next_task. Steps: start_session, then:\n{sp.brief}"
        f"{_documents(w, sp.sources)}{state.render()}\n\nThen stop.{step_hint(w)}"
    )


# ------------------------------------------------------------------------------------------------ the driver
@dataclass
class TurnReport:
    index: int
    agent: str
    name: str
    kind: str
    killed: bool = False
    result: dict[str, Any] = field(default_factory=dict)
    plexus_calls: int = 0
    transcript: str = ""
    problems: list[str] = field(default_factory=list)


_INIT_KEEP = (
    "type",
    "subtype",
    "session_id",
    "tools",
    "mcp_servers",
    "model",
    "permissionMode",
    "apiKeySource",
    "claude_code_version",
)


def sanitize_transcript(text: str, workdir: Path) -> str:
    """Make a stream-json transcript publishable: keep only the useful keys of the ``system/init`` event (it lists
    the machine's plugins, slash commands and paths) and replace the local work directory and home directory."""
    home = str(Path.home())
    subs = []
    for path, label in ((str(workdir), "<workdir>"), (home, "<home>")):
        subs += [(path, label), (path.replace("\\", "/"), label), (json.dumps(path)[1:-1], label)]
    out = []
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            ev = None
        if isinstance(ev, dict) and ev.get("type") == "system" and ev.get("subtype") == "init":
            line = json.dumps({k: ev[k] for k in _INIT_KEEP if k in ev}, separators=(",", ":"))
        for old, new in subs:
            line = line.replace(old, new)
        out.append(line)
    return "\n".join(out) + ("\n" if out else "")


class ClaudeDriver:
    """Plays turns as real ``claude -p`` processes."""

    def __init__(self, cfg: ClaudeConfig, on_event: Any = None):
        self.cfg = cfg
        self.state = TeamState()
        self.reports: list[TurnReport] = []
        self.on_event = on_event
        self.env = clean_env()
        self.incomplete: dict[str, int] = {}

    # -- scheduler entry ------------------------------------------------------------------------------------
    async def run_turn(self, w: World, turn: Turn) -> None:
        if self.cfg.stop_after_turns is not None and len(self.reports) >= self.cfg.stop_after_turns:
            raise StopRun
        if turn.kind == "init":
            prompt = init_prompt(w)
        elif turn.kind == "special":
            prompt = special_prompt(w, turn, self.state)
        else:
            lease = w.faults.builder_lease_ms if turn.agent == BUILDER else REAL_LEASE_MS
            prompt = task_prompt(w, turn, self.state, lease)
        system = role_prompt("common") + "\n" + role_prompt(turn.agent)
        rep = TurnReport(len(self.reports) + 1, turn.agent, turn.name, turn.kind)
        self.reports.append(rep)
        try:
            await self._run_process(w, turn, rep, build_command(self.cfg, prompt, system))
        finally:
            self._flush_transcript(rep)
        self._verify(w, turn, rep)

    # -- one process ----------------------------------------------------------------------------------------
    async def _run_process(self, w: World, turn: Turn, rep: TurnReport, cmd: list[str]) -> None:
        self._emit(f"--- turn {rep.index}: {turn.agent} / {turn.name}")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cfg.workdir),
            env=self.env,
            limit=16 * 1024 * 1024,
        )
        stderr_task = asyncio.create_task(proc.stderr.read())  # type: ignore[union-attr]
        pending: dict[str, tuple[str, dict[str, Any]]] = {}
        lines: list[str] = []
        try:
            async with asyncio.timeout(self.cfg.turn_timeout_s):
                async for raw in proc.stdout:  # type: ignore[union-attr]
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    lines.append(line)
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._on_stream_event(w, turn, rep, ev, pending, proc)
                await proc.wait()
        except TimeoutError:
            await _kill(proc)
            rep.problems.append(f"timeout after {self.cfg.turn_timeout_s}s")
            raise ClaudeRunError(f"turn {rep.index} ({turn.agent}/{turn.name}) timed out") from None
        except BaseException as exc:  # the fault script killed the agent, or a check failed: stop the process
            await _kill(proc)
            rep.killed = isinstance(exc, AgentKilled)
            raise
        finally:
            rep.transcript = "\n".join(lines) + ("\n" if lines else "")
            with contextlib.suppress(Exception):
                err = (await asyncio.wait_for(stderr_task, 5)).decode("utf-8", "replace").strip()
                if err:
                    rep.problems.append("stderr: " + err[-500:])
        if proc.returncode not in (0, None) and not rep.result:
            raise ClaudeRunError(f"claude exited {proc.returncode} without a result: {rep.problems}")

    def _on_stream_event(self, w, turn, rep, ev, pending, proc) -> None:
        kind = ev.get("type")
        if kind == "system" and ev.get("subtype") == "init":
            bad = [
                s
                for s in ev.get("mcp_servers", [])
                if s.get("name") == "plexus" and s.get("status") != "connected"
            ]
            if bad or not any(s.get("name") == "plexus" for s in ev.get("mcp_servers", [])):
                raise ClaudeRunError(f"Plexus MCP server did not connect: {ev.get('mcp_servers')}")
        elif kind == "assistant":
            for block in ev.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                name = block.get("name", "")
                if not name.startswith(MCP_PREFIX):
                    rep.problems.append(f"non-Plexus tool used: {name}")
                    continue
                short = name[len(MCP_PREFIX) :]
                pending[block["id"]] = (short, block.get("input") or {})
                step = w.count_call(turn.agent, short)
                rep.plexus_calls += 1
                self._emit(f"step {step:>3}  {turn.agent:<10} {short}")
        elif kind == "user":
            for block in ev.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    self._on_tool_result(w, turn, rep, block, pending)
        elif kind == "result":
            rep.result = ev
            self._check_result(turn, rep, ev)

    def _on_tool_result(self, w: World, turn: Turn, rep: TurnReport, block, pending) -> None:
        name, args = pending.pop(block.get("tool_use_id"), ("", {}))
        data = _result_json(block.get("content"))
        if block.get("is_error"):
            rep.problems.append(f"{name} failed: {str(block.get('content'))[:300]}")
            return
        if name == "claim_next_task" and data.get("task"):
            w.claimed(turn.agent, data["task"]["id"])
        elif name in ("complete_task", "fail_task"):
            done = w.released(turn.agent)
            self.state.absorb(name, args, data, task_id=str(args.get("task_id") or done or ""))
        else:
            self.state.absorb(name, args, data)
        if w.should_kill(turn.agent):
            raise AgentKilled(turn.agent, w.released(turn.agent) or "")

    def _check_result(self, turn: Turn, rep: TurnReport, ev: dict[str, Any]) -> None:
        denials = ev.get("permission_denials") or []
        if denials:
            raise ClaudeRunError(f"permission_denials in turn {rep.index}: {json.dumps(denials)[:600]}")
        if ev.get("is_error") or ev.get("subtype") != "success":
            raise ClaudeRunError(
                f"turn {rep.index} ({turn.agent}/{turn.name}) ended with subtype={ev.get('subtype')} "
                f"is_error={ev.get('is_error')}: {str(ev.get('result'))[:300]}"
            )

    # -- after a turn ---------------------------------------------------------------------------------------
    def _verify(self, w: World, turn: Turn, rep: TurnReport) -> None:
        if turn.kind == "init":
            have = set(w.statuses())
            missing = {t.id for t in w.scenario.tasks} - have
            if missing:
                raise ClaudeRunError(f"the planner did not create these tasks: {sorted(missing)}")
        elif turn.kind == "task":
            st = w.relay.task_status(turn.name)
            if st is None or st["status"] != "done":
                # An agent that ends without completing leaves its claim to expire; the scheduler then hands the task
                # to the reclaimer. Tolerate that once per task, then stop (it would only burn the budget).
                self.incomplete[turn.name] = self.incomplete.get(turn.name, 0) + 1
                rep.problems.append(f"turn ended without completing {turn.name} ({st and st['status']})")
                w.released(turn.agent)
                if self.incomplete[turn.name] > 1:
                    raise ClaudeRunError(
                        f"{turn.name} was not completed after {self.incomplete[turn.name]} attempts"
                    )
        elif turn.name == "adopt-v2" and w.relay.task_status("t12-update-endpoints-for-v2") is None:
            raise ClaudeRunError("the planner did not create t12-update-endpoints-for-v2")

    def _flush_transcript(self, rep: TurnReport) -> None:
        (self.cfg.workdir / "transcripts").mkdir(exist_ok=True)
        (self.cfg.workdir / "transcripts" / f"{rep.index:02d}-{rep.agent}-{rep.name}.jsonl").write_text(
            sanitize_transcript(rep.transcript, self.cfg.workdir), encoding="utf-8"
        )

    def _emit(self, msg: str) -> None:
        if self.on_event:
            self.on_event(msg)

    # -- the run summary for meta.json ----------------------------------------------------------------------
    def summary(self, w: World) -> dict[str, Any]:
        per_turn, usage, cost, turns, denials = [], {}, 0.0, 0, []
        for r in self.reports:
            res = r.result or {}
            u = res.get("usage") or {}
            for k in (
                "input_tokens",
                "output_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
            ):
                usage[k] = usage.get(k, 0) + int(u.get(k) or 0)
            cost += float(res.get("total_cost_usd") or 0.0)
            turns += int(res.get("num_turns") or 0)
            denials += res.get("permission_denials") or []
            per_turn.append(
                {
                    "turn": r.index,
                    "agent": r.agent,
                    "name": r.name,
                    "killed": r.killed,
                    "plexus_calls": r.plexus_calls,
                    "subtype": res.get("subtype"),
                    "is_error": res.get("is_error"),
                    "num_turns": res.get("num_turns"),
                    "duration_ms": res.get("duration_ms"),
                    "total_cost_usd": res.get("total_cost_usd"),
                    "permission_denials": res.get("permission_denials") or [],
                    "problems": r.problems,
                }
            )
        return {
            "model": self.cfg.model,
            "max_turns_per_agent_turn": self.cfg.max_turns,
            "claude_turns": turns,
            "tokens": usage,
            "total_cost_usd": round(cost, 4),
            "permission_denials": denials,
            "claude_processes": len(self.reports),
            "per_turn": per_turn,
        }

    def transcripts(self) -> dict[str, str]:
        return {
            f"{r.index:02d}-{r.agent}-{r.name}.jsonl": sanitize_transcript(r.transcript, self.cfg.workdir)
            for r in self.reports
            if r.transcript
        }


async def _kill(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError):
        proc.kill()
    with contextlib.suppress(Exception):
        await asyncio.wait_for(proc.wait(), 10)


def _result_json(content: Any) -> dict[str, Any]:
    """The JSON object a Plexus tool returned, from a ``tool_result`` content (string or list of text blocks)."""
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    if isinstance(content, str):
        try:
            val = json.loads(content)
        except json.JSONDecodeError:
            return {}
        return val if isinstance(val, dict) else {}
    return {}


# ------------------------------------------------------------------------------------------------ CLI entry
def step_numbering(client, tenant: str) -> dict[str, int]:
    """How well the agents followed the shared step counter: ToolCalls whose ``step`` is their landing position."""
    from plexus.graph.tenancy import graph_name

    calls = client.ro(graph_name(tenant), "view/flow", {"after": 0, "limit": 5000})
    ok = sum(1 for i, c in enumerate(calls, start=1) if c["step"] == i)
    return {
        "tool_calls": len(calls),
        "step_matches_global_counter": ok,
        "no_step_given": sum(1 for c in calls if c["step"] < 0),
    }


def cli_run_claude(a: argparse.Namespace) -> int:
    from plexus.cli import _client, _prepare_tenant
    from plexus.demo.recorder import record_run

    client = _client()
    run = a.run_name or time.strftime("claude-%Y%m%d-%H%M")
    tenant = a.tenant or "demo_claude"
    _prepare_tenant(client, tenant, a.reset)
    workdir = Path(tempfile.mkdtemp(prefix=f"plexus-demo-{run}-"))
    cfg = ClaudeConfig(
        workdir=workdir,
        mcp_config=write_mcp_config(workdir / "mcp.json", tenant, a.mcp_command),
        model=a.model,
        max_turns=a.max_turns,
        stop_after_turns=a.stop_after_turns,
    )
    lease = a.lease_ms if a.lease_ms is not None else REAL_BUILDER_LEASE_MS
    faults = FaultScript(
        kill_builder_at=None if a.no_faults else a.kill_at,
        publish_v2_at=None if a.no_faults else a.v2_at,
        poison_at=a.poison_at,
        builder_lease_ms=lease,
    )
    w = World(load_scenario(), faults, tenant, client)
    driver = ClaudeDriver(cfg, on_event=lambda m: print(m, flush=True))
    status, error = "completed", ""
    print(f"real Claude run '{run}': model {cfg.model}, tenant '{tenant}', workdir {workdir}", flush=True)
    try:
        asyncio.run(run_engine(w, driver))
    except StopRun:
        status = "stopped (--stop-after-turns)"
    except (ClaudeRunError, Exception) as exc:  # record what exists, then report
        status, error = "aborted", f"{type(exc).__name__}: {exc}"
    claude_meta = driver.summary(w)
    claude_meta.update(
        status=status,
        error=error,
        mcp_config=json.loads(cfg.mcp_config.read_text())["mcpServers"]["plexus"]["args"],
        step_numbering=step_numbering(client, tenant),
    )
    print(
        f"\nstatus: {status} {error}\nclaude turns: {claude_meta['claude_turns']}, cost ${claude_meta['total_cost_usd']}, "
        f"permission denials: {len(claude_meta['permission_denials'])}",
        flush=True,
    )
    for ev in w.events:
        print(f"fault/event @step {ev['step']:>3}: {ev['event']}")
    if w.step:
        meta = record_run(
            client, tenant, run, mode="claude", world=w, claude=claude_meta, transcripts=driver.transcripts()
        )
        print(
            f"recorded '{run}': {meta['inventory']['total_nodes']} nodes, {meta['inventory']['total_edges']} edges"
        )
    return 0 if status != "aborted" else 1
