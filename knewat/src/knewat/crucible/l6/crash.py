"""Family F: provenance crash-consistency (expected Plexus loss).

A writer process loops ``assert_fact`` (alternating a plain fact and one derived from the previous fact),
``record_decision`` and ``handoff`` through an arm's backend, printing one line per acknowledged call. The parent waits
for ``ready``, sleeps a random 0-400 ms and kills the process hard (``Popen.kill``: SIGKILL, or ``TerminateProcess`` on
Windows); 200 kills per arm, a new process each time, one tenant per arm. Afterwards the store is inspected:

* **orphans**: facts, decisions and handoffs with no Step/WROTE link (files: no log line carrying their id);
* **missing derived-from**: facts the writer asked to derive from an earlier fact that have no such link;
* **lost acknowledged writes**: ids the writer printed that are not in the store;
* the totals, so the counts can be read.

    python -m plexus.crucible.l6.crash run --arm P --kills 200 --port 6361
    python -m plexus.crucible.l6.crash writer --arm P ...      (internal)
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

ARMS = ("B1h", "P", "B0")
TASK = "t0"
AGENTS = ("w1", "w2")


def _open(arm: str, tenant: str, root: str, host: str, port: int) -> Any:
    from plexus.crucible.api import BackendSpec
    from plexus.crucible.backends import open_backend
    from plexus.crucible.backends.sqlite_h import SqliteHistoryBackend

    if arm == "B1h":
        return SqliteHistoryBackend(tenant, root)
    return open_backend(
        BackendSpec(
            arm="P" if arm == "P" else "B0", tenant=tenant, root=root, host=host, port=port, embedder="hash"
        )
    )


def setup(arm: str, tenant: str, root: str, host: str, port: int) -> str:
    b = _open(arm, tenant, root, host, port)
    for a in AGENTS:
        b.register_agent(a, "worker")
    b.create_tasks([{"id": TASK, "title": "kill target"}])
    sid = b.add_source("docs/kill.md")
    b.close()
    return sid


# ------------------------------------------------------------------------------------------------ the writer process
def writer(arm: str, tenant: str, root: str, host: str, port: int, source_id: str, tag: str) -> None:
    b = _open(arm, tenant, root, host, port)
    print("ready", flush=True)
    last: str | None = None
    prev_fact: str | None = None
    i = 0
    while True:
        kind = ("fact", "fact_derived", "decision", "handoff")[i % 4]
        a = AGENTS[i % 2]
        if kind in ("fact", "fact_derived") or last is None:
            derived = [prev_fact] if kind == "fact_derived" and prev_fact else []
            val = f"killrun {tag} op {i} {uuid.uuid4().hex[:10]} {'derived' if derived else 'plain'}"
            r = b.assert_fact(
                a, f"kill-subject-{tag}-{i}", "note", val, source_id=source_id, derived_from=derived
            )
            fid = r["fact_id"]
            print(json.dumps({"i": i, "kind": "fact", "id": fid, "derived": bool(derived)}), flush=True)
            prev_fact = last = fid
        elif kind == "decision":
            did = b.record_decision(a, TASK, f"killrun {tag} decision {i}", [last])
            print(json.dumps({"i": i, "kind": "decision", "id": did}), flush=True)
        else:
            hid = b.handoff(a, AGENTS[(i + 1) % 2], TASK, f"killrun {tag} handoff {i}", [], [last])
            print(json.dumps({"i": i, "kind": "handoff", "id": hid}), flush=True)
        i += 1


# ------------------------------------------------------------------------------------------------ the parent
def kill_rounds(
    cmd_for: Callable[[int], list[str]],
    kills: int,
    seed: int,
    *,
    env: dict[str, str] | None = None,
    progress: Callable[[int, list[dict[str, Any]]], None] | None = None,
) -> list[dict[str, Any]]:
    """One writer process per round: wait for its ``ready`` line, kill it hard after a random 0-400 ms, and return the
    JSON lines it printed (its acknowledged calls). Shared by the F families (``crash``, ``crash_tasks``, ``verify_crash``)."""
    rng = random.Random(seed)
    acked: list[dict[str, Any]] = []
    for k in range(kills):
        p = subprocess.Popen(
            cmd_for(k), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env
        )
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
        if progress:
            progress(k, acked)
    return acked


def kill_loop(
    arm: str, kills: int, root: str, tenant: str, host: str, port: int, seed: int, log: Any = print
) -> dict[str, Any]:
    sid = setup(arm, tenant, root, host, port)

    def cmd_for(k: int) -> list[str]:
        return [
            sys.executable, "-m", "plexus.crucible.l6.crash", "writer", "--arm", arm, "--tenant", tenant, "--root", root,
            "--host", host, "--port", str(port), "--source", sid, "--tag", f"{seed}k{k}",
        ]  # fmt: skip

    def progress(k: int, acked: list[dict[str, Any]]) -> None:
        if (k + 1) % 20 == 0:
            log(f"F {arm}: {k + 1}/{kills} kills, {len(acked)} acknowledged writes so far")

    acked = kill_rounds(cmd_for, kills, seed, progress=progress)
    res = verify(arm, tenant, root, host, port, acked)
    res["kills"] = kills
    res["acknowledged_writes"] = len(acked)
    return res


# ------------------------------------------------------------------------------------------------ verification
def verify(
    arm: str, tenant: str, root: str, host: str, port: int, acked: list[dict[str, Any]]
) -> dict[str, Any]:
    ids = {k: [a["id"] for a in acked if a["kind"] == k] for k in ("fact", "decision", "handoff")}
    if arm == "P":
        return _verify_plexus(tenant, host, port, ids)
    if arm == "B1h":
        return _verify_sqlite(Path(root) / "B1" / tenant / "crucible.db", ids)
    return _verify_files(Path(root) / "B0" / tenant, ids)


def _shape(
    totals: dict[str, int],
    orphans: dict[str, int],
    missing_derived: int,
    lost: dict[str, int],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    n = sum(totals.values())
    out = {
        "totals": totals, "orphans": orphans, "orphans_total": sum(orphans.values()),
        "missing_derived_from": missing_derived, "lost_acknowledged": lost, "lost_acknowledged_total": sum(lost.values()),
        "rule_of_three_upper_pct": round(300 / max(1, n), 2) if sum(orphans.values()) + missing_derived + sum(lost.values()) == 0 else None,
    }  # fmt: skip
    if extra:
        out.update(extra)
    return out


def _verify_plexus(tenant: str, host: str, port: int, ids: dict[str, list[str]]) -> dict[str, Any]:
    from plexus.graph.client import GraphClient
    from plexus.graph.tenancy import graph_name

    c = GraphClient(host=host, port=port)
    g = c.graph(graph_name(tenant))

    def n(q: str, p: dict | None = None) -> int:
        return int(g.ro_query(q, p or {}).result_set[0][0])

    totals = {
        "facts": n("MATCH (f:Fact) WHERE f.value STARTS WITH 'killrun' RETURN count(f)"),
        "decisions": n("MATCH (d:Decision) WHERE d.text STARTS WITH 'killrun' RETURN count(d)"),
        "handoffs": n("MATCH (h:Handoff) WHERE h.note STARTS WITH 'killrun' RETURN count(h)"),
    }
    orphans = {
        "facts": n(
            "MATCH (f:Fact) WHERE f.value STARTS WITH 'killrun' AND NOT (:Step)-[:WROTE]->(f) RETURN count(f)"
        ),
        "decisions": n(
            "MATCH (d:Decision) WHERE d.text STARTS WITH 'killrun' AND NOT (:Step)-[:WROTE]->(d) RETURN count(d)"
        ),
        "handoffs": n(
            "MATCH (h:Handoff) WHERE h.note STARTS WITH 'killrun' AND NOT (:Step)-[:WROTE]->(h) RETURN count(h)"
        ),
    }
    missing = n(
        "MATCH (f:Fact) WHERE f.value STARTS WITH 'killrun' AND f.value ENDS WITH ' derived' "
        "AND NOT (f)-[:DERIVED_FROM]->(:Fact) RETURN count(f)"
    )
    lost = {}
    for kind, label in (("fact", "Fact"), ("decision", "Decision"), ("handoff", "Handoff")):
        have = {
            r[0]
            for r in g.ro_query(
                f"MATCH (x:{label}) WHERE x.id IN $ids RETURN x.id", {"ids": ids[kind]}
            ).result_set
        }
        lost[kind + "s"] = len(set(ids[kind]) - have)
    c.close()
    return _shape(totals, orphans, missing, lost)


def _verify_sqlite(path: Path, ids: dict[str, list[str]]) -> dict[str, Any]:
    c = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)

    def n(q: str) -> int:
        return int(c.execute(q).fetchone()[0])

    totals = {
        "facts": n("SELECT count(*) FROM facts WHERE value LIKE 'killrun%'"),
        "decisions": n("SELECT count(*) FROM decisions WHERE text LIKE 'killrun%'"),
        "handoffs": n("SELECT count(*) FROM handoffs WHERE note LIKE 'killrun%'"),
    }
    orphans = {
        "facts": n(
            "SELECT count(*) FROM facts f WHERE f.value LIKE 'killrun%' AND NOT EXISTS (SELECT 1 FROM step_wrote w WHERE w.node_id=f.id)"
        ),
        "decisions": n(
            "SELECT count(*) FROM decisions d WHERE d.text LIKE 'killrun%' AND NOT EXISTS (SELECT 1 FROM step_wrote w WHERE w.node_id=d.id)"
        ),
        "handoffs": n(
            "SELECT count(*) FROM handoffs h WHERE h.note LIKE 'killrun%' AND NOT EXISTS (SELECT 1 FROM step_wrote w WHERE w.node_id=h.id)"
        ),
    }
    missing = n(
        "SELECT count(*) FROM facts f WHERE f.value LIKE 'killrun%' AND f.value LIKE '% derived' "
        "AND NOT EXISTS (SELECT 1 FROM fact_links l WHERE l.src=f.id AND l.kind='derived_from' AND l.dst IN (SELECT id FROM facts))"
    )
    lost = {}
    for kind, table in (("fact", "facts"), ("decision", "decisions"), ("handoff", "handoffs")):
        have = (
            {
                r[0]
                for r in c.execute(
                    f"SELECT id FROM {table} WHERE id IN ({','.join('?' * len(ids[kind]))})", ids[kind]
                )
            }
            if ids[kind]
            else set()
        )
        lost[kind + "s"] = len(set(ids[kind]) - have)
    c.close()
    return _shape(totals, orphans, missing, lost)


def _verify_files(d: Path, ids: dict[str, list[str]]) -> dict[str, Any]:
    facts: dict[str, dict[str, Any]] = {}
    for line in (d / "MEMORY.md").read_text(encoding="utf-8").splitlines():
        if " <!--" in line:
            try:
                f = json.loads(line.rsplit(" <!--", 1)[1].removesuffix("-->"))
            except json.JSONDecodeError:
                continue
            if str(f.get("value", "")).startswith("killrun"):
                facts[f["id"]] = f
    corrupt = 0

    def jl(path: Path) -> list[dict[str, Any]]:
        nonlocal corrupt
        out = []
        if path.exists():
            for ln in path.read_text(encoding="utf-8").splitlines():
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    corrupt += 1
        return out

    decisions = {
        r["id"]: r for r in jl(d / "decisions.jsonl") if str(r.get("text", "")).startswith("killrun")
    }
    handoffs = {r["id"]: r for r in jl(d / "handoffs.jsonl") if str(r.get("note", "")).startswith("killrun")}
    logged: set[str] = set()
    for p in (d / "logs").glob("*.jsonl"):
        for r in jl(p):
            for key in ("fact_id", "id"):
                if r.get(key):
                    logged.add(r[key])
    totals = {"facts": len(facts), "decisions": len(decisions), "handoffs": len(handoffs)}
    orphans = {
        "facts": sum(1 for i in facts if i not in logged),
        "decisions": sum(1 for i in decisions if i not in logged),
        "handoffs": sum(1 for i in handoffs if i not in logged),
    }
    missing = sum(
        1 for i, f in facts.items() if str(f["value"]).endswith(" derived") and not f.get("derived_from")
    )
    lost = {
        "facts": len(set(ids["fact"]) - set(facts)),
        "decisions": len(set(ids["decision"]) - set(decisions)),
        "handoffs": len(set(ids["handoff"]) - set(handoffs)),
    }
    return _shape(totals, orphans, missing, lost, {"corrupt_lines": corrupt})


# ------------------------------------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l6-crash")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("writer")
    r = sub.add_parser("run")
    for p in (w, r):
        p.add_argument("--arm", choices=ARMS, required=True)
        p.add_argument("--host", default="127.0.0.1")
        p.add_argument("--port", type=int, default=6361)
        p.add_argument("--tenant", default="")
        p.add_argument("--root", default="")
    w.add_argument("--source", required=True)
    w.add_argument("--tag", required=True)
    r.add_argument("--kills", type=int, default=200)
    r.add_argument("--seed", type=int, default=20261016)
    r.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "writer":
        writer(a.arm, a.tenant, a.root, a.host, a.port, a.source, a.tag)
        return 0
    root = a.root or tempfile.mkdtemp(prefix="l6f-")
    tenant = a.tenant or f"l6f_{a.arm.lower()}_{uuid.uuid4().hex[:6]}"
    try:
        res = kill_loop(
            a.arm, a.kills, root, tenant, a.host, a.port, a.seed, log=lambda s: print(s, flush=True)
        )
    finally:
        if a.arm == "P":
            from plexus.graph.client import GraphClient
            from plexus.graph.tenancy import graph_name

            GraphClient(host=a.host, port=a.port).delete_graph(graph_name(tenant))
        if not a.root:
            shutil.rmtree(root, ignore_errors=True)
    res["arm"] = a.arm
    print(json.dumps(res, indent=1))
    if a.out:
        a.out.write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
