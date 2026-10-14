"""Equal-budget baseline answerer: unmodified ``claude -p`` over a context, strict JSON out, cached on disk.

One process per question, single shot:

    claude -p --model sonnet --max-turns 3 --tools "" --strict-mcp-config --output-format stream-json --verbose \\
           --no-session-persistence --disable-slash-commands --append-system-prompt <role>   < context + question

* ``ANTHROPIC_API_KEY`` is removed from the environment (usage goes to the signed-in subscription, D-002);
* no tools at all (``--tools ""``), so the model cannot read anything but what it is given; the context travels on
  stdin because a 32k-character prompt does not fit a Windows command line and the spec only allows *reading a
  provided context*; ``permission_denials`` and any ``tool_use`` block are checked and fail the question;
* the process runs in an empty scratch directory (no project ``CLAUDE.md``);
* the reply must be exactly ``{"answer": ...}`` (:func:`plexus.crucible.l2.questions.parse_reply`).

Answers are cached by sha256 of (model, prompt version, role prompt, context, question), so a re-run costs nothing.
The cache keeps the reply, usage, cost and latency of the call that produced it (``cached=True`` marks reuse).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plexus.crucible.l2.questions import CONVENTIONS, Question, parse_reply

PROMPT_VERSION = "l2-v1"
ROLE = (
    "You answer one question about a recorded run of a three-agent software team (planner, researcher, builder). "
    "Use only the material you are given; it is synthetic data. Work out the answer carefully from it, but do not "
    'invent anything it does not support. Your final reply must be exactly one JSON object {"answer": ...} in the '
    "format the question asks for, with no other text."
)


class BudgetExceeded(RuntimeError):
    """The cumulative cost of non-cached calls reached the cap; the run stops without losing what it has."""


@dataclass
class LlmCall:
    qid: str
    arm: str
    reply: str = ""
    answer: Any = None
    parse_error: str = ""
    error: str = ""  # process / protocol failure (not a wrong answer)
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    duration_api_ms: float = 0.0
    num_turns: int = 0
    model: str = ""
    permission_denials: list[Any] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    session_id: str = ""
    cached: bool = False
    key: str = ""

    @property
    def total_tokens(self) -> int:
        return sum(int(self.usage.get(k, 0) or 0) for k in USAGE_KEYS)

    def to_json(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d.pop("cached")
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> LlmCall:
        return cls(**d, cached=True)


USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


def clean_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env.pop("ANTHROPIC_API_KEY", None)
    return env


def cache_key(model: str, context: str, q: Question) -> str:
    h = hashlib.sha256()
    for part in (PROMPT_VERSION, model, ROLE, CONVENTIONS, context, q.prompt()):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def build_prompt(context: str, q: Question) -> str:
    return f"{context.rstrip()}\n\n---\n{CONVENTIONS}\n\n{q.prompt()}\n"


class ClaudeRunner:
    def __init__(
        self,
        model: str = "sonnet",
        *,
        cache_dir: Path | None = None,
        max_turns: int = 3,
        timeout_s: int = 300,
        launcher: list[str] | None = None,  # tests: a stand-in for the claude executable
        budget_usd: float | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ):
        self.model, self.max_turns, self.timeout_s = model, max_turns, timeout_s
        self.cache_dir = cache_dir
        self.launcher = launcher
        self.budget_usd = budget_usd
        self.spent_usd = 0.0
        self.calls = 0
        self._cwd = cwd
        self._env = env
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    # -- command ---------------------------------------------------------------------------------------------
    def binary(self) -> list[str]:
        return self.launcher or [shutil.which("claude") or "claude"]

    def command(self) -> list[str]:
        return [
            *self.binary(),
            "-p",
            "--model",
            self.model,
            "--max-turns",
            str(self.max_turns),
            "--tools",
            "",
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--output-format",
            "stream-json",
            "--verbose",
            "--no-session-persistence",
            "--append-system-prompt",
            ROLE,
        ]

    # -- one question ---------------------------------------------------------------------------------------------
    def _path(self, arm: str, qid: str, key: str) -> Path | None:
        return self.cache_dir / arm / f"{qid}-{key[:16]}.json" if self.cache_dir else None

    def ask(self, arm: str, q: Question, context: str, *, use_cache: bool = True) -> LlmCall:
        key = cache_key(self.model, context, q)
        path = self._path(arm, q.id, key)
        if use_cache and path is not None and path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            if d.get("key") == key and not d.get("error"):
                call = LlmCall.from_json(d)
                call.answer, call.parse_error = parse_reply(
                    call.reply
                )  # the parser may be newer than the cache
                return call
        if self.budget_usd is not None and self.spent_usd >= self.budget_usd:
            raise BudgetExceeded(f"spent ${self.spent_usd:.2f} of the ${self.budget_usd:.2f} cap")
        call = self._run(arm, q, context)
        call.key = key
        self.spent_usd += call.cost_usd
        self.calls += 1
        if path is not None and not call.error:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(call.to_json(), indent=1, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        return call

    def _run(self, arm: str, q: Question, context: str) -> LlmCall:
        call = LlmCall(qid=q.id, arm=arm, model=self.model)
        cwd = self._cwd or Path(tempfile.mkdtemp(prefix="crucible-l2-cwd-"))
        cwd.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(
                self.command(),
                input=build_prompt(context, q).encode("utf-8"),
                capture_output=True,
                cwd=str(cwd),
                env=self._env if self._env is not None else clean_env(),
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            call.latency_ms = (time.perf_counter() - t0) * 1000
            call.error = f"timeout after {self.timeout_s}s"
            return call
        call.latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        out = proc.stdout.decode("utf-8", "replace")
        result: dict[str, Any] | None = None
        for line in out.splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = ev.get("type")
            if kind == "assistant":
                for block in ev.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use":
                        call.tools_used.append(block.get("name", "?"))
            elif kind == "system" and ev.get("subtype") == "init":
                call.session_id = ev.get("session_id", "")
            elif kind == "result":
                result = ev
        if result is None:
            err = proc.stderr.decode("utf-8", "replace").strip()[-300:]
            call.error = f"no result event (exit {proc.returncode}): {err}"
            return call
        call.reply = str(result.get("result") or "")
        call.usage = {k: int((result.get("usage") or {}).get(k) or 0) for k in USAGE_KEYS}
        call.cost_usd = float(result.get("total_cost_usd") or 0.0)
        call.duration_api_ms = float(result.get("duration_api_ms") or 0.0)
        call.num_turns = int(result.get("num_turns") or 0)
        call.permission_denials = list(result.get("permission_denials") or [])
        mu = result.get("modelUsage") or {}
        if mu:
            call.model = ", ".join(sorted(mu))
        if call.permission_denials:
            call.error = f"permission_denials: {json.dumps(call.permission_denials)[:300]}"
        elif call.tools_used:
            call.error = f"the model used tools: {call.tools_used}"
        elif result.get("is_error") or result.get("subtype") != "success":
            call.error = f"result subtype={result.get('subtype')} is_error={result.get('is_error')}: {call.reply[:200]}"
        else:
            call.answer, call.parse_error = parse_reply(call.reply)
        return call
