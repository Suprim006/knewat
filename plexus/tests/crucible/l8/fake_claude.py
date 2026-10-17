"""A stand-in for ``claude -p`` used by the L8 harness tests ($0, no model).

It parses the prompt the harness passes, performs a scripted version of the assignment against the arm's real store
(P: PlexusBackend on the tenant from mcp.json; B1: the SQLite backend at --root; B0': files in the work directory),
writes the artifact file into the working directory, and prints stream-json events shaped like Claude Code's
(``system/init``, ``assistant`` tool_use, ``user`` tool_result, ``result``). Behaviour knob (env ``L8_FAKE_MODE``):

* ``memory`` (default): a value the team already recorded is taken from team memory, never re-read from the code;
  so after a commit the agent acts on the stale token (the scorer must count it);
* ``reread``: every value is read from ``repo/`` at the time of the action (no stale acts possible).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

MODE = os.environ.get("L8_FAKE_MODE", "memory")
SUBJECT = "Acme Notes API S21"
PAUSE = float(os.environ.get("L8_FAKE_PAUSE", "0.15"))


def emit(ev: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(ev) + "\n")
    sys.stdout.flush()
    time.sleep(PAUSE)


def args_of(argv: list[str]) -> dict[str, str]:
    out = {}
    for i, a in enumerate(argv):
        if a.startswith("--") and i + 1 < len(argv):
            out[a] = argv[i + 1]
    out["-p"] = argv[argv.index("-p") + 1]
    return out


class Fake:
    def __init__(self, argv: list[str]):
        a = args_of(argv)
        self.prompt = a["-p"]
        cfg = json.loads(Path(a["--mcp-config"]).read_text(encoding="utf-8"))
        self.mcp = bool(cfg["mcpServers"])
        self.cwd = Path.cwd()
        self.backend = None
        m = re.search(r"agent_id is '(\w+)'", self.prompt)
        self.agent = m.group(1) if m else "planner"
        if self.mcp:
            srv = cfg["mcpServers"]["plexus"]
            sargs = srv["args"]
            tenant = sargs[sargs.index("--tenant") + 1]
            from plexus.crucible.api import BackendSpec
            from plexus.crucible.backends import open_backend

            if "--root" in sargs:
                self.backend = open_backend(
                    BackendSpec(arm="B1", tenant=tenant, root=sargs[sargs.index("--root") + 1])
                )
            else:
                env = srv["env"]
                self.backend = open_backend(BackendSpec(
                    arm="P-mcp", tenant=tenant, root="", host=env["FALKORDB_HOST"], port=int(env["FALKORDB_PORT"]),
                    embedder="hash"))  # fmt: skip
        emit({"type": "system", "subtype": "init", "model": "fake-sonnet", "claude_code_version": "fake",
              "mcp_servers": [{"name": "plexus", "status": "connected"}] if self.mcp else []})  # fmt: skip
        self.n = 0

    # -- tool helpers ---------------------------------------------------------------------------------------
    def call(self, name: str, inp: dict[str, Any], fn: Any) -> Any:
        self.n += 1
        tid = f"toolu_{uuid.uuid4().hex[:12]}"
        emit(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]},
            }
        )
        try:
            res = fn()
            content = res if isinstance(res, str) else json.dumps(res)
            err = False
        except Exception as exc:  # noqa: BLE001
            content, err, res = f"{type(exc).__name__}: {exc}", True, None
        emit({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": content,
                                                       "is_error": err}]}})  # fmt: skip
        return res

    def mcp_call(self, short: str, **inp: Any) -> Any:
        b = self.backend
        a = self.agent
        fns = {
            "start_session": lambda: (b.register_agent(a, a), {"session_id": f"session-{a}"})[1],
            "claim_next_task": lambda: {"task": b.claim_next_task(a, inp["lease_ms"])},
            "assert_fact": lambda: b.assert_fact(a, inp["subject"], inp["predicate"], inp["value"]),
            "recall": lambda: {"facts": b.recall(a, inp["query"], k=inp.get("k", 8))},
            "complete_task": lambda: b.complete_task(a, inp["task_id"], inp["expected_version"], inp["artifacts"]),
            "create_tasks": lambda: {"task_ids": b.create_tasks(inp["tasks"])},
            "record_decision": lambda: {"decision_id": b.record_decision(a, inp["task_id"], inp["text"], inp.get("based_on_fact_ids", []))},
            "handoff": lambda: {"handoff_id": b.handoff(a, inp["to_agent"], inp["task_id"], inp["note"], [], inp.get("fact_ids", []))},
        }  # fmt: skip
        return self.call(f"mcp__plexus__{short}", {"agent_id": a, **inp}, fns[short])

    def read(self, rel: str) -> str:
        p = self.cwd / rel
        return self.call(
            "Read", {"file_path": str(p)}, lambda: p.read_text(encoding="utf-8") if p.exists() else ""
        )

    def write(self, rel: str, text: str) -> None:
        p = self.cwd / rel

        def go() -> str:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
            return f"File created successfully at: {p}"

        self.call("Write", {"file_path": str(p), "content": text}, go)

    # -- values ----------------------------------------------------------------------------------------------
    def code_value(self, setting: str) -> str:
        mod, fn = setting.split(".")
        text = self.read(f"repo/{mod}.py") or ""
        m = re.search(rf"def {fn}\(\):\n(?:.*\n)*?\s+return \"(AX-\d{{5}})\"", text)
        return m.group(1) if m else "DELETED"

    def memory_value(self, setting: str) -> str | None:
        if self.mcp:
            r = self.mcp_call("recall", query=setting, k=5) or {}
            for h in r.get("facts", []):
                if h.get("predicate") == setting and h.get("status", "active") == "active":
                    return h["value"]
            return None
        p = self.cwd / "memory" / "facts.md"
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        hits = re.findall(rf"^{re.escape(setting)} = (AX-\d{{5}})", text, re.M)
        return hits[-1] if hits else None

    def value(self, setting: str) -> str:
        if MODE == "memory":
            v = self.memory_value(setting)
            if v:
                return v
        return self.code_value(setting)

    # -- assignments ------------------------------------------------------------------------------------------
    def run(self) -> None:
        p = self.prompt
        if "project kickoff" in p:
            tasks = json.loads(p[p.index("[") : p.rindex("]") + 1])
            if self.mcp:
                self.mcp_call("start_session")
                self.mcp_call("create_tasks", tasks=tasks)
            else:
                self.write("memory/tasks.md", "\n".join(f"- {t['id']}: open" for t in tasks) + "\n")
        elif "(event: adopt-v2)" in p:
            if self.mcp:
                self.mcp_call("start_session")
                self.mcp_call("create_tasks", tasks=[{"id": "t12-update-endpoints-for-v2", "title": "Update endpoint design for API v2",
                                                      "priority": 60, "depends_on": ["t03-design-endpoints"]}])  # fmt: skip
            else:
                self.write("memory/decisions.md", "- adopt v2\n")
        elif "(event: ingest-v2)" in p:
            if self.mcp:
                self.mcp_call("start_session")
                self.mcp_call("assert_fact", subject=SUBJECT, predicate="api_version", value="v2")
        else:
            self.task()
        emit({"type": "result", "subtype": "success", "is_error": False, "num_turns": self.n, "total_cost_usd": 0.0,
              "usage": {"input_tokens": 10 * self.n, "output_tokens": 5 * self.n, "cache_creation_input_tokens": 0,
                        "cache_read_input_tokens": 100 * self.n}, "permission_denials": []})  # fmt: skip

    def task(self) -> None:
        from plexus.crucible.l8.scenario import TASK_BY_ID

        tid = re.search(r"Task id: (\S+)", self.prompt).group(1)
        t = TASK_BY_ID[tid]
        version = 0
        if self.mcp:
            self.mcp_call("start_session")
            lease = int(re.search(r"lease_ms=(\d+)", self.prompt).group(1))
            got = self.mcp_call("claim_next_task", lease_ms=lease) or {}
            version = (got.get("task") or {}).get("version", 0)
        for r in t.records:
            v = self.code_value(r)
            if self.mcp:
                self.mcp_call("assert_fact", subject=SUBJECT, predicate=r, value=v)
            else:
                p = self.cwd / "memory" / "facts.md"
                old = p.read_text(encoding="utf-8") if p.exists() else ""
                self.write("memory/facts.md", old + f"{r} = {v}\n")
        vals = {n: self.value(n) for n in t.needs}
        body = "\n".join(f"{n}: {v}" for n, v in vals.items())
        self.write(t.artifact_path, f"# {t.title}\n\n{body}\n")
        summary = "values: " + ", ".join(vals.values())
        if self.mcp:
            self.mcp_call("complete_task", task_id=tid, expected_version=version,
                          artifacts=[{"kind": "file", "uri": t.artifact_path, "summary": summary}])  # fmt: skip
        else:
            p = self.cwd / "memory" / "tasks.md"
            old = p.read_text(encoding="utf-8") if p.exists() else ""
            self.write("memory/tasks.md", old + f"- {tid}: done ({summary})\n")


if __name__ == "__main__":
    Fake(sys.argv[1:]).run()
