"""The three LLM arms of the L6 pilot: B1a (SQL tool), B0g (files + shell tools) and B0r (one-shot reader).

Every call is one ``claude -p`` process (Sonnet, ``ANTHROPIC_API_KEY`` removed, ``--no-session-persistence``, never
``--bare``), run from an empty temporary directory (B0g: from a copy of the arm's files), with the question on stdin.
Replies are parsed with the L2 rule (prose allowed, must END with one ``{"answer": ...}`` object), cached by
sha256(prompt version, model, arm, role, tool configuration, data hash, question), and the cache is re-parsed on load.
A total cap, a per-arm cap and a per-call ``--max-budget-usd`` guard bound the spend; a call that would start past a cap
raises :class:`BudgetExceeded` instead of running.

The prompts below are FROZEN once the first paid call is made (``PROMPT_VERSION``); results record the commit.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from plexus.crucible.l2.llm import USAGE_KEYS, BudgetExceeded
from plexus.crucible.l2.questions import parse_reply

PROMPT_VERSION = "l6-v1"
MODEL = "sonnet"
PER_CALL_CAP_USD = 0.80
MAX_TURNS = {"B0r": 3, "B1a": 20, "B0g": 20, "P": 20}
# P: the real Plexus MCP server, read-only tools only (the write tools, quarantine_source above all, are not allowed)
P_TOOLS = ("impact", "why", "blocked_by_failure", "task_status", "who_knew", "fact_history")
ALLOWED_TOOLS = {
    "B0r": set(),
    "B1a": {"mcp__sql__query"},
    "B0g": {"Bash", "Read", "Grep", "Glob"},
    "P": {f"mcp__plexus__{t}" for t in P_TOOLS},
}

COMMON = (
    "All the data is synthetic. Work out the answer carefully from the data; do not guess and do not invent ids. "
    'Your final reply must END with exactly one JSON object {"answer": ...} in the format the question asks for, '
    "with nothing after it. You may reason in prose before it."
)

SCHEMA_NOTE = """\
The database (SQLite) has these tables of interest:
  sources(id, uri)                      -- source documents
  facts(id, entity_name, predicate, value, scope, status, valid_from, ...)
                                        -- a fact; `value` is its text; `status` is active | superseded | forgotten;
                                           `valid_from` is the time the fact was recorded (epoch ms; use it for "earliest");
                                           `scope` is the sprint scope for sprint data, else 'global'
  fact_agents(fact_id, agent_id, at)    -- who asserted the fact
  fact_links(src, dst, kind)            -- kind='derived_from': fact `src` derives from `dst`, which is a SOURCE id or another
                                           FACT id; kind='supersedes': fact `src` replaced fact `dst`
  steps(id, agent_id, n, at)            -- one step of an agent
  step_reads(step_id, fact_id)          -- the facts a step read
  decisions(id, agent_id, task_id, text, at)
  decision_facts(decision_id, fact_id)  -- the facts a decision is based on
  handoffs(id, from_agent, to_agent, task_id, note, at)
  handoff_items(handoff_id, kind, item_id) -- kind='fact': the facts a handoff carries
  tasks(id, status, ...), deps(task_id, dep_id)  -- task `task_id` depends on task `dep_id`
The database may be large; a statement is killed after 20 seconds, so write efficient queries."""

FILES_NOTE = """\
Your working directory holds the team's files (one record per line, JSON):
  facts.jsonl      {"id","text","agent","at","status","scope","derived_from":[parent ids: a source id or a fact id],"supersedes":[fact ids]}
                   status is active | superseded | forgotten; `at` is the recording time (epoch ms; use it for "earliest")
  sources.json     [{"id","uri"}]
  decisions.jsonl  {"id","text","agent","at","based_on":[fact ids]}
  handoffs.jsonl   {"id","from","to","at","carries":[fact ids]}
  tasks.json       [{"id","status","depends_on":[task ids]}]
  logs/<agent>.jsonl  {"step","n","at","read":[fact ids]}: the facts that agent read in each step
Use the tools you have (Bash with python or grep, Read, Grep, Glob). The files may be large, so prefer a short script to reading them whole."""

CONVENTIONS_D = (
    "Sprints are tagged S001..S200. A fact's scope is `scope:Sxxx`; a decision or handoff belongs to the sprint of the facts it is based on / carries "
    "(all in one sprint). A fact is `superseded` when its status says so (a newer fact replaced it) and `forgotten` when its status says so. "
    "Shared sources have ids starting `shared-`; a decision cites a source through the facts it is based on."
)

ROLES = {
    "B1a": (
        "You answer one question about a team's recorded memory. You have ONE tool, `query`, that runs a read-only SQL statement on the memory "
        "database. " + SCHEMA_NOTE + " " + COMMON
    ),
    "P": (
        "You answer one question about a team's recorded memory, kept in the Plexus graph memory. You have its read-only tools "
        "(`impact`, `why`, `blocked_by_failure`, `task_status`, `who_knew`, `fact_history`); each tool describes itself. Facts are "
        "recorded with their provenance: a fact derives from a source or from other facts, decisions are based on facts, handoffs "
        "carry facts, steps read facts. Use the tools; do not guess and do not invent ids. If no tool can give a part of the answer, "
        "say so in prose and give your best answer for the rest. " + COMMON
    ),
    "B0g": (
        "You answer one question about a team's recorded memory, kept in files. " + FILES_NOTE + " " + COMMON
    ),
    "B0r": (
        "You answer one question about a team's recorded memory. You have no tools: you are shown excerpts of the memory files (the lines "
        "most relevant to the question by keyword, at most 32,000 characters; the files are much larger and the excerpt may be incomplete). "
        "File formats: facts.jsonl {id,text,agent,at,status,scope,derived_from[],supersedes[]}; decisions.jsonl {id,text,agent,at,based_on[]}; "
        "handoffs.jsonl {id,from,to,at,carries[]}; logs/<agent>.jsonl {step,n,at,read[]}; sources.json [{id,uri}]. "
        "If the excerpt cannot support an answer, give your best answer from what is shown. " + COMMON
    ),
}


@dataclass
class Call:
    qid: str
    arm: str
    family: str
    reply: str = ""
    answer: Any = None
    parse_error: str = ""
    error: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    num_turns: int = 0
    model: str = ""
    tools_used: list[str] = field(default_factory=list)
    permission_denials: list[Any] = field(default_factory=list)
    key: str = ""
    cached: bool = False
    context_chars: int = 0

    @property
    def total_tokens(self) -> int:
        return sum(int(self.usage.get(k, 0) or 0) for k in USAGE_KEYS)

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("cached")
        return d


def clean_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def question_prompt(qid: str, text: str, fmt: str) -> str:
    return f"Question {qid}: {text}\nAnswer format: {fmt}\n"


class PilotRunner:
    def __init__(
        self,
        cache_dir: Path,
        *,
        total_cap: float = 20.0,
        arm_caps: dict[str, float] | None = None,
        launcher: list[str] | None = None,
        model: str = MODEL,
        db_host: str = "127.0.0.1",
        db_port: int = 6361,
    ):
        self.cache_dir, self.total_cap, self.model = cache_dir, total_cap, model
        self.db_host, self.db_port = db_host, db_port
        self.arm_caps = arm_caps or {}
        self.launcher = launcher
        self.live_calls = 0
        self._lock = threading.Lock()
        cache_dir.mkdir(parents=True, exist_ok=True)
        # the caps are cumulative over every invocation: what the cache already holds was paid for
        self.arm_spent: dict[str, float] = {}
        for p in cache_dir.glob("*/*.json"):
            try:
                self.arm_spent[p.parent.name] = self.arm_spent.get(p.parent.name, 0.0) + float(
                    json.loads(p.read_text(encoding="utf-8")).get("cost_usd", 0.0)
                )
            except (OSError, ValueError):
                continue
        self.spent = sum(self.arm_spent.values())
        self.spent_before = self.spent

    # -- keys ---------------------------------------------------------------------------------------------------------------------
    @staticmethod
    def tool_config(arm: str) -> str:
        return {
            "B0r": "tools=none max_turns=3 stdin",
            "B1a": f"tools=mcp__sql__query(read-only sql, 20s, 200 rows, 12000 chars) max_turns={MAX_TURNS['B1a']}",
            "B0g": f"tools=Bash,Read,Grep,Glob max_turns={MAX_TURNS['B0g']} cwd=copy of the files",
            "P": f"tools=plexus-mcp stdio, allowed {','.join(P_TOOLS)} max_turns={MAX_TURNS['P']} embedder=hash",
        }[arm]

    def key(self, arm: str, prompt: str, data_sha: str) -> str:
        h = hashlib.sha256()
        for part in (PROMPT_VERSION, self.model, arm, ROLES[arm], self.tool_config(arm), data_sha, prompt):
            h.update(part.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def _path(self, arm: str, qid: str, key: str) -> Path:
        return self.cache_dir / arm / f"{qid}-{key[:16]}.json"

    # -- commands ------------------------------------------------------------------------------------------------------------------
    def binary(self) -> list[str]:
        return self.launcher or [shutil.which("claude") or "claude"]

    def command(self, arm: str, mcp_config: Path | None) -> list[str]:
        base = [
            *self.binary(), "-p", "--model", self.model, "--max-turns", str(MAX_TURNS[arm]), "--disable-slash-commands",
            "--output-format", "stream-json", "--verbose", "--no-session-persistence",
            "--max-budget-usd", str(PER_CALL_CAP_USD), "--append-system-prompt", ROLES[arm],
        ]  # fmt: skip
        if arm == "B0r":
            return [*base, "--tools", "", "--strict-mcp-config"]
        if arm == "B1a":
            assert mcp_config is not None
            return [
                *base,
                "--tools",
                "",
                "--strict-mcp-config",
                "--mcp-config",
                str(mcp_config),
                "--allowedTools",
                "mcp__sql__query",
            ]
        if arm == "P":
            assert mcp_config is not None
            allowed = ",".join(f"mcp__plexus__{t}" for t in P_TOOLS)
            return [
                *base,
                "--tools",
                "",
                "--strict-mcp-config",
                "--mcp-config",
                str(mcp_config),
                "--allowedTools",
                allowed,
            ]
        return [
            *base,
            "--tools",
            "Bash,Read,Grep,Glob",
            "--strict-mcp-config",
            "--allowedTools",
            "Bash,Read,Grep,Glob",
        ]

    # -- one call -------------------------------------------------------------------------------------------------------------------
    def ask(
        self, arm: str, family: str, qid: str, prompt: str, *, data_sha: str, context: str = "", db: str = "", files_dir: Path | None = None,
        use_cache: bool = True, tenant: str = "",
    ) -> Call:  # fmt: skip
        key = self.key(arm, prompt + "\x00" + context, data_sha)
        path = self._path(arm, qid, key)
        if use_cache and path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            if d.get("key") == key and (
                not d.get("error") or str(d["error"]).startswith(("max_turns", "budget"))
            ):
                call = Call(**d, cached=True)
                if call.reply:
                    call.answer, call.parse_error = parse_reply(
                        call.reply
                    )  # the parser may be newer than the cache
                return call
        with self._lock:
            if self.spent >= self.total_cap:
                raise BudgetExceeded(f"total ${self.spent:.2f} of the ${self.total_cap:.2f} cap")
            cap = self.arm_caps.get(arm)
            if cap is not None and self.arm_spent.get(arm, 0.0) >= cap:
                raise BudgetExceeded(f"{arm} ${self.arm_spent.get(arm, 0.0):.2f} of its ${cap:.2f} cap")
        call = self._run(arm, family, qid, prompt, context, db, files_dir, tenant)
        call.key = key
        call.context_chars = len(context)
        with self._lock:
            self.spent += call.cost_usd
            self.arm_spent[arm] = self.arm_spent.get(arm, 0.0) + call.cost_usd
            self.live_calls += 1
        if not call.error or call.error.startswith(("max_turns", "budget")):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(call.to_json(), indent=1, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        return call

    def _run(
        self,
        arm: str,
        family: str,
        qid: str,
        prompt: str,
        context: str,
        db: str,
        files_dir: Path | None,
        tenant: str = "",
    ) -> Call:
        call = Call(qid=qid, arm=arm, family=family, model=self.model)
        tmp = Path(tempfile.mkdtemp(prefix="crucible-l6-cwd-"))
        mcp_config = None
        try:
            cwd = tmp
            if arm == "B1a":
                mcp_config = tmp / "mcp.json"
                mcp_config.write_text(
                    json.dumps(
                        {
                            "mcpServers": {
                                "sql": {
                                    "command": sys.executable,
                                    "args": ["-m", "plexus.crucible.l6.sql_mcp", "--db", db],
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                cwd = tmp / "cwd"
                cwd.mkdir()
            elif arm == "P":
                mcp_config = tmp / "mcp.json"
                mcp_config.write_text(
                    json.dumps(
                        {
                            "mcpServers": {
                                "plexus": {
                                    "command": str(
                                        Path(sys.executable).parent
                                        / ("plexus-mcp.exe" if os.name == "nt" else "plexus-mcp")
                                    ),
                                    "args": ["--transport", "stdio", "--tenant", tenant],
                                    "env": {
                                        "FALKORDB_HOST": self.db_host,
                                        "FALKORDB_PORT": str(self.db_port),
                                        "PLEXUS_EMBEDDER": "hash",
                                    },
                                }
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                cwd = tmp / "cwd"
                cwd.mkdir()
            elif arm == "B0g":
                assert files_dir is not None
                cwd = tmp / "data"
                shutil.copytree(files_dir, cwd)
            stdin = (context.rstrip() + "\n\n---\n" if context else "") + prompt
            t0 = time.perf_counter()
            try:
                proc = subprocess.run(
                    self.command(arm, mcp_config), input=stdin.encode("utf-8"), capture_output=True, cwd=str(cwd), env=clean_env(),
                    timeout=900 if arm != "B0r" else 300,
                )  # fmt: skip
            except subprocess.TimeoutExpired:
                call.latency_ms = (time.perf_counter() - t0) * 1000
                call.error = "timeout"
                return call
            call.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
            result: dict[str, Any] | None = None
            for line in proc.stdout.decode("utf-8", "replace").splitlines():
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("type") == "assistant":
                    for block in ev.get("message", {}).get("content", []):
                        if block.get("type") == "tool_use":
                            call.tools_used.append(block.get("name", "?"))
                elif ev.get("type") == "result":
                    result = ev
            if result is None:
                call.error = f"no result event (exit {proc.returncode}): {proc.stderr.decode('utf-8', 'replace').strip()[-300:]}"
                return call
            call.reply = str(result.get("result") or "")
            call.usage = {k: int((result.get("usage") or {}).get(k) or 0) for k in USAGE_KEYS}
            call.cost_usd = float(result.get("total_cost_usd") or 0.0)
            call.num_turns = int(result.get("num_turns") or 0)
            call.permission_denials = list(result.get("permission_denials") or [])
            mu = result.get("modelUsage") or {}
            if mu:
                call.model = ", ".join(sorted(mu))
            bad = [t for t in call.tools_used if t not in ALLOWED_TOOLS[arm]]
            sub = result.get("subtype")
            if bad:
                call.error = f"disallowed tool use: {bad}"
            elif call.permission_denials:
                call.error = f"permission_denials: {json.dumps(call.permission_denials)[:300]}"
            elif sub == "error_max_turns":
                call.error = "max_turns"
            elif sub and "budget" in str(sub):
                call.error = "budget (per-call cap)"
            elif result.get("is_error") or sub != "success":
                call.error = f"result subtype={sub} is_error={result.get('is_error')}: {call.reply[:200]}"
            if call.reply and not bad and not call.permission_denials:
                call.answer, call.parse_error = parse_reply(call.reply)
            return call
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
