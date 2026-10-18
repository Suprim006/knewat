"""Subprocess entry point for C2: claim one task, keep heartbeating, wait to be killed.

``python -m plexus.crucible.victim '<BackendSpec json>' <agent_id> <lease_ms> <heartbeat_ms>``

Prints ``CLAIMED <task_id> <version>`` once it holds a task. The harness then ``SIGKILL``s the process (on Windows
``TerminateProcess``): no cleanup code runs, exactly like a crashed agent.
"""

from __future__ import annotations

import json
import sys
import time

from plexus.crucible.api import BackendSpec
from plexus.crucible.backends import open_backend


def main(argv: list[str]) -> int:
    spec = BackendSpec.from_json(json.loads(argv[1]))
    agent_id, lease_ms, hb_ms = argv[2], int(argv[3]), int(argv[4])
    b = open_backend(spec)
    b.register_agent(agent_id, "victim")
    deadline = time.monotonic() + 60
    task = None
    while task is None and time.monotonic() < deadline:
        task = b.claim_next_task(agent_id, lease_ms)
        if task is None:
            time.sleep(0.02)
    if task is None:
        print("NOTHING", flush=True)
        return 1
    print(f"CLAIMED {task['id']} {task['version']}", flush=True)
    while True:  # killed from outside
        time.sleep(hb_ms / 1000.0)
        b.heartbeat(agent_id, task["id"], lease_ms)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
