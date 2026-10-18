"""P12-F3 kill test: a writer process loops assert_fact / record_decision / verify_fact(changed) and is SIGKILLed.

Inspector: an old fact that was superseded by a verification (a successor ``SUPERSEDES`` it) must have either a completed
verification (``VERIFIED_BY {outcome:'changed'}``) or the ``verify_degraded`` marker; otherwise the interruption is
*silent*. Also counted: Decisions BASED_ON such a silent fact that are not flagged.

    python -m plexus.crucible.l6.verify_crash run --kills 40 --port 6377

``PLEXUS_TEST_VERIFY_GAP_MS`` (test hook in the Staleness service) sleeps between the supersede and the backdate so the
kill window is wide enough to be hit; it is set for the writer processes by :func:`kill_loop`.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import threading
import time
import uuid
from typing import Any

AGENT = "w1"
TASK = "t0"
GAP_MS = "60"


def _services(host: str, port: int, graph: str) -> tuple[Any, Any, Any, Any]:
    from plexus.embed import HashEmbedder
    from plexus.engram import Engram
    from plexus.graph.client import GraphClient
    from plexus.relay import Relay
    from plexus.staleness import Staleness

    c = GraphClient(host=host, port=port)
    eng = Engram(c, graph, HashEmbedder())
    return c, eng, Relay(c, graph), Staleness(c, graph, engram=eng)


def setup(host: str, port: int, graph: str) -> str:
    from plexus.graph.schema import apply_schema

    c, eng, relay, _ = _services(host, port, graph)
    apply_schema(c, graph)
    scope = eng.create_scope("project", "vcrash")
    relay.register_agent(AGENT, AGENT, "worker", "test")
    relay.create_tasks([{"id": TASK, "title": "kill target"}])
    c.close()
    return scope


def writer(host: str, port: int, graph: str, scope: str, tag: str) -> None:
    c, eng, relay, stale = _services(host, port, graph)
    print("ready", flush=True)
    i = 0
    while True:
        r = eng.assert_fact(f"vsubj-{tag}-{i}", "note", f"vcrash {tag} {i} old", scope, AGENT, supersede=True)
        fid = r["fact_id"]
        did = relay.record_decision(AGENT, TASK, f"vcrash decision {tag} {i}", [fid])
        print(json.dumps({"i": i, "fact": fid, "decision": did}), flush=True)
        stale.verify_fact(fid, False, new_value=f"vcrash {tag} {i} new", agent_id=AGENT)
        print(json.dumps({"i": i, "verified": fid}), flush=True)
        i += 1


def inspect(host: str, port: int, graph: str) -> dict[str, Any]:
    from plexus.graph.client import GraphClient

    c = GraphClient(host=host, port=port)
    g = c.graph(graph)
    rows = g.ro_query(
        "MATCH (n:Fact)-[:SUPERSEDES]->(o:Fact) WHERE o.value STARTS WITH 'vcrash' "
        "RETURN o.id, coalesce(o.verify_degraded, false), "
        "[(o)-[r:VERIFIED_BY]->() | r.outcome], "
        "[(d:Decision)-[:BASED_ON]->(o) | coalesce(d.flagged, false)]"
    ).result_set
    marked_only = silent = silent_unflagged = completed = 0
    for _oid, degraded, outcomes, flags in rows:
        if "changed" in outcomes:
            completed += 1
        elif degraded:
            marked_only += 1
        else:
            silent += 1
            silent_unflagged += sum(1 for f in flags if not f)
    # old facts killed before the supersede but after the marker: active, marked
    pre_supersede = g.ro_query(
        "MATCH (o:Fact {verify_degraded: true, status: 'active'}) WHERE o.value STARTS WITH 'vcrash' "
        "RETURN count(o)"
    ).result_set[0][0]
    c.close()
    return {
        "superseded_by_verify": len(rows),
        "completed": completed,
        "marked_unfinished": marked_only,
        "silent": silent,
        "silent_unflagged_decisions": silent_unflagged,
        "marked_before_supersede": int(pre_supersede),
    }


def kill_loop(kills: int, host: str, port: int, graph: str, seed: int, log: Any = print) -> dict[str, Any]:
    scope = setup(host, port, graph)
    rng = random.Random(seed)
    env = {**os.environ, "PLEXUS_TEST_VERIFY_GAP_MS": GAP_MS}
    for k in range(kills):
        cmd = [
            sys.executable, "-m", "plexus.crucible.l6.verify_crash", "writer", "--host", host,
            "--port", str(port), "--graph", graph, "--scope", scope, "--tag", f"{seed}k{k}",
        ]  # fmt: skip
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
        ready = threading.Event()

        def pump(proc: subprocess.Popen = p, ev: threading.Event = ready) -> None:
            assert proc.stdout is not None
            for ln in proc.stdout:
                if ln.strip() == "ready":
                    ev.set()

        t = threading.Thread(target=pump, daemon=True)
        t.start()
        if not ready.wait(60):
            p.kill()
            raise RuntimeError(f"writer {k} never became ready")
        time.sleep(rng.uniform(0.0, 0.4))
        p.kill()
        p.wait()
        t.join(5)
        if (k + 1) % 20 == 0:
            log(f"{k + 1}/{kills} kills")
    res = inspect(host, port, graph)
    res["kills"] = kills
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="verify-crash")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("writer")
    r = sub.add_parser("run")
    for p in (w, r):
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=6377)
        p.add_argument("--graph", default="")
    w.add_argument("--scope", required=True)
    w.add_argument("--tag", required=True)
    r.add_argument("--kills", type=int, default=40)
    r.add_argument("--seed", type=int, default=20261016)
    a = ap.parse_args(argv)
    if a.cmd == "writer":
        writer(a.host, a.port, a.graph, a.scope, a.tag)
        return 0
    from plexus.graph.client import GraphClient

    graph = a.graph or f"vcrash_{uuid.uuid4().hex[:6]}"
    try:
        print(json.dumps(kill_loop(a.kills, a.host, a.port, graph, a.seed), indent=1))
    finally:
        GraphClient(host=a.host, port=a.port).delete_graph(graph)
    return 0


if __name__ == "__main__":
    sys.exit(main())
