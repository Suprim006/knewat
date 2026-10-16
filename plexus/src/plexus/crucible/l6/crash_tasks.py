"""Family F, Task variant (P12 fix 2): provenance crash-consistency of the five task tools.

A writer process loops ``create_tasks`` / ``claim_next_task`` / ``complete_task`` / ``fail_task`` / ``reopen_task``
through the ``P-mcp`` backend (``Runtime._run``: Step + WROTE + ToolCall exactly as the server does) and prints one
line per acknowledged call. The parent waits for ``ready``, sleeps a random 0-400 ms and kills the process hard
(``Popen.kill``); a new writer per kill. Afterwards the store is inspected.

**Orphan definition.** Every call that changes a task changes it exactly once, and every such change is also one
``(Step)-[:WROTE]->(Task)`` edge: ``create_tasks`` makes the task at ``version`` 0, and ``claim_next_task``,
``complete_task``, ``fail_task`` and ``reopen_task`` each add 1 to ``version`` (``heartbeat`` is not used here). So a
Task must have exactly ``version + 1`` incoming ``WROTE`` edges from Steps. The shortfall summed over all tasks is
the number of **orphaned task writes** (a state change committed without its provenance edge); a task with any
shortfall is an **orphan task**. A surplus would be a duplicate edge and is counted separately. **Lost acknowledged
writes**: a task id the writer printed that is not in the store, or whose ``version`` is below the one the call
returned.

    python -m plexus.crucible.l6.crash_tasks run --kills 50 --port 6376 [--legacy]

``--legacy`` takes the five tools out of ``FOLDS_WROTE`` inside the writer process, i.e. the pre-fix behaviour (the
write statement, then a second ``link_step`` statement), so the harness can show what the fix removes.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Any

AGENTS = ("w1", "w2")
TASK_TOOLS = ("create_tasks", "claim_next_task", "complete_task", "fail_task", "reopen_task")
CYCLE = ("create", "claim", "complete", "create", "claim", "fail", "reopen", "claim", "complete")


def _open(tenant: str, root: str, host: str, port: int) -> Any:
    from plexus.crucible.api import BackendSpec
    from plexus.crucible.backends import open_backend

    return open_backend(
        BackendSpec(arm="P-mcp", tenant=tenant, root=root, host=host, port=port, embedder="hash")
    )


def setup(tenant: str, root: str, host: str, port: int) -> None:
    b = _open(tenant, root, host, port)
    for a in AGENTS:
        b.register_agent(a, "worker")
    b.close()


# ------------------------------------------------------------------------------------------------ the writer process
def writer(tenant: str, root: str, host: str, port: int, tag: str, legacy: bool) -> None:
    if legacy:
        from plexus.mcp import lineage_hook

        lineage_hook.FOLDS_WROTE = frozenset({"assert_fact", "record_decision", "handoff"})
    b = _open(tenant, root, host, port)
    print("ready", flush=True)
    held: list[tuple[str, int]] = []  # (task id, version) claimed by this writer, not yet finished
    failed: list[str] = []
    i = 0
    while True:
        op = CYCLE[i % len(CYCLE)]
        a = AGENTS[0]  # one acting agent per writer process keeps claim/complete ownership simple
        if op == "create":
            ids = [f"kt-{tag}-{i}-{n}" for n in range(3)]
            tasks = [{"id": t, "title": f"killrun {tag} task {t}", "priority": n} for n, t in enumerate(ids)]
            b.create_tasks(tasks)
            print(json.dumps({"i": i, "op": op, "ids": ids, "version": 0}), flush=True)
        elif op == "claim":
            r = b.claim_next_task(a, 60_000)
            if r is not None:
                held.append((r["id"], int(r["version"])))
                print(
                    json.dumps({"i": i, "op": op, "ids": [held[-1][0]], "version": held[-1][1]}), flush=True
                )
        elif op in ("complete", "fail") and held:
            tid, ver = held.pop()
            if op == "complete":
                res = b.complete_task(a, tid, ver, [{"kind": "file", "uri": f"kill/{tag}/{i}.txt"}])
            else:
                res = b.fail_task(a, tid, ver, [], "killrun failure")
                failed.append(tid)
            print(json.dumps({"i": i, "op": op, "ids": [tid], "version": int(res["version"])}), flush=True)
        elif op == "reopen" and failed:
            tid = failed.pop()
            res = b.reopen_task(a, tid)
            print(json.dumps({"i": i, "op": op, "ids": [tid], "version": int(res["version"])}), flush=True)
        i += 1


# ------------------------------------------------------------------------------------------------ the parent
def kill_loop(
    kills: int,
    root: str,
    tenant: str,
    host: str,
    port: int,
    seed: int,
    legacy: bool = False,
    log: Any = print,
) -> dict[str, Any]:
    setup(tenant, root, host, port)
    rng = random.Random(seed)
    acked: list[dict[str, Any]] = []
    for k in range(kills):
        cmd = [
            sys.executable, "-m", "plexus.crucible.l6.crash_tasks", "writer", "--tenant", tenant, "--root", root,
            "--host", host, "--port", str(port), "--tag", f"{seed}k{k}",
        ]  # fmt: skip
        if legacy:
            cmd.append("--legacy")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        lines: list[str] = []
        ready = threading.Event()

        def pump(proc: subprocess.Popen = p, out: list[str] = lines, ev: threading.Event = ready) -> None:
            assert proc.stdout is not None
            for ln in proc.stdout:
                if ln.strip() == "ready":
                    ev.set()
                else:
                    out.append(ln)

        t = threading.Thread(target=pump, daemon=True)
        t.start()
        if not ready.wait(60):
            p.kill()
            raise RuntimeError(f"writer {k} never became ready")
        time.sleep(rng.uniform(0.0, 0.4))
        p.kill()
        p.wait()
        t.join(5)
        for ln in lines:
            try:
                acked.append(json.loads(ln))
            except json.JSONDecodeError:
                pass  # the last line may be cut by the kill: it was not acknowledged
        if (k + 1) % 10 == 0:
            log(f"F-tasks: {k + 1}/{kills} kills, {len(acked)} acknowledged calls so far")
    res = verify(tenant, host, port, acked)
    res["kills"] = kills
    res["acknowledged_calls"] = len(acked)
    res["legacy"] = legacy
    return res


# ------------------------------------------------------------------------------------------------ verification
def verify(tenant: str, host: str, port: int, acked: list[dict[str, Any]]) -> dict[str, Any]:
    from plexus.graph.client import GraphClient
    from plexus.graph.tenancy import graph_name

    c = GraphClient(host=host, port=port)
    g = c.graph(graph_name(tenant))
    r = g.ro_query(
        "MATCH (t:Task) WHERE t.title STARTS WITH 'killrun' "
        "OPTIONAL MATCH (:Step)-[w:WROTE]->(t) "
        "WITH t, count(w) AS wc, t.version + 1 AS expected "
        "RETURN count(t), sum(expected), sum(wc), "
        "sum(CASE WHEN wc < expected THEN expected - wc ELSE 0 END), "
        "sum(CASE WHEN wc < expected THEN 1 ELSE 0 END), "
        "sum(CASE WHEN wc > expected THEN wc - expected ELSE 0 END)"
    ).result_set[0]
    versions = {
        row[0]: int(row[1])
        for row in g.ro_query(
            "MATCH (t:Task) WHERE t.title STARTS WITH 'killrun' RETURN t.id, t.version"
        ).result_set
    }
    c.close()
    lost = sum(1 for a in acked for tid in a["ids"] if versions.get(tid, -1) < a["version"])
    return {
        "totals": {"tasks": int(r[0]), "expected_wrote_edges": int(r[1]), "wrote_edges": int(r[2])},
        "orphan_writes": int(r[3]),
        "orphan_tasks": int(r[4]),
        "duplicate_wrote_edges": int(r[5]),
        "lost_acknowledged_total": lost,
    }


# ------------------------------------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l6-crash-tasks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("writer")
    r = sub.add_parser("run")
    for p in (w, r):
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=6361)
        p.add_argument("--tenant", default="")
        p.add_argument("--root", default="")
        p.add_argument("--legacy", action="store_true")
    w.add_argument("--tag", required=True)
    r.add_argument("--kills", type=int, default=50)
    r.add_argument("--seed", type=int, default=20261018)
    a = ap.parse_args(argv)
    if a.cmd == "writer":
        writer(a.tenant, a.root, a.host, a.port, a.tag, a.legacy)
        return 0
    root = a.root or tempfile.mkdtemp(prefix="l6ft-")
    tenant = a.tenant or f"l6ft_{uuid.uuid4().hex[:6]}"
    try:
        res = kill_loop(
            a.kills, root, tenant, a.host, a.port, a.seed, a.legacy, log=lambda s: print(s, flush=True)
        )
    finally:
        from plexus.graph.client import GraphClient
        from plexus.graph.tenancy import graph_name

        GraphClient(host=a.host, port=a.port).delete_graph(graph_name(tenant))
        if not a.root:
            shutil.rmtree(root, ignore_errors=True)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
