"""A stand-in for ``claude -p`` used by the orchestrator tests (no LLM, no subscription).

It speaks the same ``--output-format stream-json`` protocol: it reads the generated ``--mcp-config`` for the tenant and
database, plays the assignment it is given in the prompt directly against the graph through the Relay service, and
prints ``system`` / ``assistant`` (tool_use) / ``user`` (tool_result) / ``result`` events as Claude Code does.
Env switches: ``FAKE_DENY=1`` ends with a permission denial, ``FAKE_HANG_BUILDER=1`` makes the builder sleep after
its first working call so the orchestrator has to kill it.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

from knewat.graph.client import GraphClient
from knewat.graph.schema import apply_schema
from knewat.graph.tenancy import graph_name
from knewat.relay import Relay

_n = 0


def emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def tool(name: str, args: dict, run) -> dict:
    global _n
    _n += 1
    tid = f"toolu_{_n}"
    emit(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": tid, "name": f"mcp__knewat__{name}", "input": args}]
            },
        }
    )
    data = run()
    emit(
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tid,
                        "content": [{"type": "text", "text": json.dumps(data)}],
                    }
                ]
            },
        }
    )
    return data


def main() -> None:
    argv = sys.argv[1:]
    prompt = argv[argv.index("-p") + 1]
    cfg = json.load(open(argv[argv.index("--mcp-config") + 1], encoding="utf-8"))["mcpServers"]["knewat"]
    tenant = cfg["args"][cfg["args"].index("--tenant") + 1]
    client = GraphClient(host=cfg["env"]["FALKORDB_HOST"], port=int(cfg["env"]["FALKORDB_PORT"]))
    apply_schema(client, graph_name(tenant))  # the real MCP server does this on first use
    relay = Relay(client, graph_name(tenant))
    agent = re.search(r"agent_id is '(\w+)'", prompt).group(1)  # type: ignore[union-attr]
    emit({"type": "system", "subtype": "init", "mcp_servers": [{"name": "knewat", "status": "connected"}]})
    tool(
        "start_session",
        {"agent_id": agent},
        lambda: {"session_id": "s", "agent": relay.register_agent(agent, agent, agent, "fake")},
    )
    denied = []
    if "project kickoff" in prompt:
        specs = json.loads(prompt[prompt.index("[\n") : prompt.index("\n]") + 2])
        tool(
            "create_tasks",
            {"agent_id": agent, "tasks": specs},
            lambda: {"task_ids": relay.create_tasks(specs)},
        )
    elif "do NOT call claim_next_task" in prompt:  # an event turn
        if "adopt-v2" in prompt:
            spec = [
                {
                    "id": "t12-update-endpoints-for-v2",
                    "title": "v2",
                    "priority": 60,
                    "depends_on": ["t03-design-endpoints"],
                }
            ]
            tool(
                "create_tasks",
                {"agent_id": agent, "tasks": spec},
                lambda: {"task_ids": relay.create_tasks(spec)},
            )
    else:
        task_id = re.search(r"Task id: (\S+)", prompt).group(1)  # type: ignore[union-attr]
        lease = int(re.search(r"lease_ms=(\d+)", prompt).group(1))  # type: ignore[union-attr]
        claim = tool(
            "claim_next_task",
            {"agent_id": agent, "lease_ms": lease},
            lambda: {"task": relay.claim_next_task(agent, lease)},
        )
        task = claim["task"]
        assert task and task["id"] == task_id, (task, task_id)
        if "abandoned by" in prompt:
            tool("remember_episode", {"agent_id": agent, "text": "took over"}, lambda: {"episode_id": "e"})
        tool("recall", {"agent_id": agent, "query": "API version"}, lambda: {"facts": [], "count": 0})
        if agent == "builder" and task_id == "t03-design-endpoints" and os.environ.get("FAKE_HANG_BUILDER"):
            # (only the first attempt: the reclaimed run is done by the researcher)
            time.sleep(120)
        tool(
            "complete_task",
            {"agent_id": agent, "task_id": task_id, "expected_version": task["version"]},
            lambda: relay.complete_task(
                agent, task_id, task["version"], [{"kind": "file", "uri": f"a/{task_id}"}]
            ),
        )
    if os.environ.get("FAKE_DENY"):
        denied = [{"tool_name": "Bash", "tool_input": {}}]
    emit(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "num_turns": _n,
            "total_cost_usd": 0.001,
            "duration_ms": 10,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "permission_denials": denied,
            "result": "done",
        }
    )


if __name__ == "__main__":
    main()
