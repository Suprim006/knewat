"""Loaders: put one :class:`World` into SQLite (B1h / B1a), FalkorDB (P arms) and plain files (B0g / B0r).

Each loader returns the node/edge counts it ended with, and :func:`check_counts` compares them with the ledger
(``World.counts``) so that no question is asked of an arm that holds a different story. The SQLite file uses the B1
schema of ``backends/sqlite.py`` plus the ``claims`` table of ``sqlite_h`` (the store is the B1 store; only the bulk
insert differs). ``tuned=True`` adds the two indexes and runs ``ANALYZE`` (BEAT_SQL §2.2); ``tuned=False`` is the
"untuned SQL" sensitivity row.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from plexus.crucible.backends.sqlite_h import SqliteHistoryBackend
from plexus.crucible.l6.world import T0, World
from plexus.graph.client import GraphClient
from plexus.graph.tenancy import graph_name

OPEN = 9_999_999_999_999
BATCH = 4000


def chunks(rows: list[Any], n: int = BATCH) -> Iterator[list[Any]]:
    for i in range(0, len(rows), n):
        yield rows[i : i + n]


def check_counts(world: World, got: dict[str, int], arm: str) -> None:
    want = world.counts()
    bad = {k: (want[k], got.get(k)) for k in got if k in want and got[k] != want[k]}
    if bad:
        raise AssertionError(f"{arm}: store differs from the ledger (ledger, store): {bad}")


# ------------------------------------------------------------------------------------------------ SQLite
def build_sqlite(world: World, root: Path, tenant: str, *, tuned: bool = True) -> tuple[str, dict[str, int]]:
    """Create ``<root>/B1/<tenant>/crucible.db`` holding the world. Returns (path, counts read back from the file)."""
    b = SqliteHistoryBackend(tenant, root)
    path = b.path
    b.close()
    c = sqlite3.connect(path)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=OFF")
    c.execute("BEGIN")
    c.executemany(
        "INSERT OR IGNORE INTO agents(id, role, created_at) VALUES(?,?,?)",
        [(a, "", T0) for a in world.agents],
    )
    c.executemany(
        "INSERT INTO sources(id, uri, kind, trust, created_at) VALUES(?,?,?,?,?)",
        [(s["id"], s["uri"], "doc", 1.0, T0) for s in world.sources],
    )
    frows, arows, lrows = [], [], []
    for f in world.facts:
        vt = OPEN if f["status"] == "active" else f["at"] + 1
        frows.append((f["id"], f["topic"], f["topic"], "note", f["text"], f["text"].lower(), "", f["scope"],
                      f["status"], f["at"], vt, f["at"], 1.0))  # fmt: skip
        arows.append((f["id"], f["agent"], f["at"]))
        lrows += [(f["id"], p, "derived_from") for p in f["parents"]]
    c.executemany("INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", frows)
    c.executemany("INSERT INTO fact_agents(fact_id, agent_id, at) VALUES(?,?,?)", arows)
    lrows += [(new, old, "supersedes") for new, old in world.supersedes]
    c.executemany("INSERT INTO fact_links(src, dst, kind) VALUES(?,?,?)", lrows)
    sid = {s["id"]: i for i, s in enumerate(world.steps, start=1)}
    c.executemany(
        "INSERT INTO steps(id, agent_id, n, at) VALUES(?,?,?,?)",
        [(sid[s["id"]], s["agent"], s["n"], s["at"]) for s in world.steps],
    )
    c.executemany(
        "INSERT INTO step_reads(step_id, fact_id) VALUES(?,?)",
        [(sid[s["id"]], r) for s in world.steps for r in s["reads"]],
    )
    c.executemany(
        "INSERT INTO decisions(id, agent_id, task_id, text, at, flagged) VALUES(?,?,?,?,?,0)",
        [(d["id"], d["agent"], d["task"], d["text"], d["at"]) for d in world.decisions],
    )
    c.executemany(
        "INSERT INTO decision_facts(decision_id, fact_id) VALUES(?,?)",
        [(d["id"], f) for d in world.decisions for f in d["based_on"]],
    )
    c.executemany(
        "INSERT INTO handoffs(id, from_agent, to_agent, task_id, note, at) VALUES(?,?,?,?,?,?)",
        [(h["id"], h["from"], h["to"], "t0", "", h["at"]) for h in world.handoffs],
    )
    c.executemany(
        "INSERT INTO handoff_items(handoff_id, kind, item_id) VALUES(?,?,?)",
        [(h["id"], "fact", f) for h in world.handoffs for f in h["carries"]],
    )
    c.executemany(
        "INSERT INTO tasks(id, title, priority, seq, status, created_at) VALUES(?,?,0,?,?,?)",
        [(t["id"], t["id"], i, t["status"], T0) for i, t in enumerate(world.tasks)],
    )
    c.executemany(
        "INSERT INTO deps(task_id, dep_id) VALUES(?,?)",
        [(t["id"], d) for t in world.tasks for d in t["deps"]],
    )
    c.execute("COMMIT")
    if tuned:
        c.execute("CREATE INDEX IF NOT EXISTS step_reads_fact ON step_reads(fact_id)")
        c.execute("CREATE INDEX IF NOT EXISTS handoff_items_item ON handoff_items(item_id)")
        c.execute("ANALYZE")
    c.execute("PRAGMA synchronous=NORMAL")
    got = sqlite_counts(c)
    c.close()
    check_counts(world, got, "B1h")
    return path, got


def sqlite_counts(c: sqlite3.Connection) -> dict[str, int]:
    def n(sql: str) -> int:
        return int(c.execute(sql).fetchone()[0])

    return {
        "agents": n("SELECT count(*) FROM agents"), "sources": n("SELECT count(*) FROM sources"),
        "facts": n("SELECT count(*) FROM facts"),
        "derived_edges": n("SELECT count(*) FROM fact_links WHERE kind='derived_from'"),
        "steps": n("SELECT count(*) FROM steps"), "reads": n("SELECT count(*) FROM step_reads"),
        "decisions": n("SELECT count(*) FROM decisions"), "based_on": n("SELECT count(*) FROM decision_facts"),
        "handoffs": n("SELECT count(*) FROM handoffs"), "carries": n("SELECT count(*) FROM handoff_items"),
        "tasks": n("SELECT count(*) FROM tasks"), "depends_on": n("SELECT count(*) FROM deps"),
        "supersedes": n("SELECT count(*) FROM fact_links WHERE kind='supersedes'"),
    }  # fmt: skip


# ------------------------------------------------------------------------------------------------ FalkorDB
def load_plexus(world: World, client: GraphClient, tenant: str) -> tuple[str, dict[str, int]]:
    """Drop and recreate the tenant graph with the model-v1 nodes and edges the L6 queries (and the product) read."""
    name = graph_name(tenant)
    client.delete_graph(name)
    g = client.graph(name)
    # range indexes on `id` only (what every L6 query seeks on). The product's full-text and vector indexes are left out:
    # they are not read by any L6 statement and make a 50,000-fact bulk load take minutes.
    for label in ("Agent", "Source", "Fact", "Step", "Decision", "Handoff", "Task", "Scope"):
        g.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")

    def run(cypher: str, rows: list[Any]) -> None:
        for ch in chunks(rows):
            g.query(cypher, {"rows": ch})

    run(
        "UNWIND $rows AS r CREATE (:Agent {id: r.id, name: r.id, created_at: r.t})",
        [{"id": a, "t": T0} for a in world.agents],
    )
    run(
        "UNWIND $rows AS r CREATE (:Source {id: r.id, uri: r.uri, kind: 'doc', trust: 'normal', title: '', text: '', created_at: r.t})",
        [{"id": s["id"], "uri": s["uri"], "t": T0} for s in world.sources],
    )
    run(
        "UNWIND $rows AS r CREATE (:Task {id: r.id, title: r.id, status: r.status, priority: 0, lease_until: 0, "
        "claimed_by: '', version: 0, done_at: 0, created_at: r.t, seq: r.seq})",
        [{"id": t["id"], "status": t["status"], "t": T0, "seq": i} for i, t in enumerate(world.tasks)],
    )
    edges = [{"a": t["id"], "b": d} for t in world.tasks for d in t["deps"]]
    run(
        "UNWIND $rows AS r MATCH (a:Task {id: r.a}) MATCH (b:Task {id: r.b}) CREATE (a)-[:DEPENDS_ON]->(b)",
        edges,
    )
    if world.scopes:
        run(
            "UNWIND $rows AS r CREATE (:Scope {id: r.id, kind: 'project', name: r.name, created_at: r.t})",
            [{"id": s["id"], "name": s["name"], "t": T0} for s in world.scopes],
        )
    run(
        "UNWIND $rows AS r CREATE (:Fact {id: r.id, predicate: 'note', value: r.text, subject_id: r.topic, "
        "status: r.status, valid_from: r.at, valid_to: r.vt, created_at: r.at, scope_id: r.scope})",
        [{"id": f["id"], "text": f["text"], "topic": f["topic"], "status": f["status"], "at": f["at"],
          "vt": OPEN if f["status"] == "active" else f["at"] + 1, "scope": f["scope"]} for f in world.facts],
    )  # fmt: skip
    run(
        "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) MATCH (a:Agent {id: r.a}) CREATE (f)-[:ASSERTED_BY]->(a)",
        [{"f": f["id"], "a": f["agent"]} for f in world.facts],
    )
    if world.scopes:
        run(
            "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) MATCH (s:Scope {id: r.s}) CREATE (f)-[:IN_SCOPE]->(s)",
            [{"f": f["id"], "s": f["scope"]} for f in world.facts],
        )
    src_ids = {s["id"] for s in world.sources}
    to_src = [{"f": f["id"], "p": p} for f in world.facts for p in f["parents"] if p in src_ids]
    to_fact = [{"f": f["id"], "p": p} for f in world.facts for p in f["parents"] if p not in src_ids]
    run(
        "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) MATCH (p:Source {id: r.p}) CREATE (f)-[:DERIVED_FROM]->(p)",
        to_src,
    )
    run(
        "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) MATCH (p:Fact {id: r.p}) CREATE (f)-[:DERIVED_FROM]->(p)",
        to_fact,
    )
    run(
        "UNWIND $rows AS r MATCH (n:Fact {id: r.n}) MATCH (o:Fact {id: r.o}) CREATE (n)-[:SUPERSEDES]->(o)",
        [{"n": n, "o": o} for n, o in world.supersedes],
    )
    run(
        "UNWIND $rows AS r MATCH (a:Agent {id: r.a}) CREATE (s:Step {id: r.id, n: r.n, at: r.at, agent_id: r.a, "
        "created_at: r.at}) CREATE (s)-[:BY]->(a)",
        [{"id": s["id"], "n": s["n"], "at": s["at"], "a": s["agent"]} for s in world.steps],
    )
    run(
        "UNWIND $rows AS r MATCH (s:Step {id: r.s}) MATCH (f:Fact {id: r.f}) CREATE (s)-[:READ {via: 'use', at: r.at}]->(f)",
        [{"s": s["id"], "f": f, "at": s["at"]} for s in world.steps for f in s["reads"]],
    )
    run(
        "UNWIND $rows AS r MATCH (a:Agent {id: r.a}) MATCH (t:Task {id: r.t}) "
        "CREATE (d:Decision {id: r.id, text: r.text, at: r.at, created_at: r.at}) "
        "CREATE (a)-[:DECIDED]->(d) CREATE (d)-[:FOR]->(t)",
        [
            {"id": d["id"], "text": d["text"], "at": d["at"], "a": d["agent"], "t": d["task"]}
            for d in world.decisions
        ],
    )
    run(
        "UNWIND $rows AS r MATCH (d:Decision {id: r.d}) MATCH (f:Fact {id: r.f}) CREATE (d)-[:BASED_ON]->(f)",
        [{"d": d["id"], "f": f} for d in world.decisions for f in d["based_on"]],
    )
    run(
        "UNWIND $rows AS r MATCH (a:Agent {id: r.a}) MATCH (b:Agent {id: r.b}) MATCH (t:Task {id: 't0'}) "
        "CREATE (h:Handoff {id: r.id, at: r.at, note: '', created_at: r.at}) "
        "CREATE (h)-[:FROM]->(a) CREATE (h)-[:TO]->(b) CREATE (h)-[:FOR]->(t)",
        [{"id": h["id"], "at": h["at"], "a": h["from"], "b": h["to"]} for h in world.handoffs],
    )
    run(
        "UNWIND $rows AS r MATCH (h:Handoff {id: r.h}) MATCH (f:Fact {id: r.f}) CREATE (h)-[:CARRIES]->(f)",
        [{"h": h["id"], "f": f} for h in world.handoffs for f in h["carries"]],
    )
    got = plexus_counts(g)
    check_counts(world, got, "P")
    return name, got


def plexus_counts(g: Any) -> dict[str, int]:
    def n(q: str) -> int:
        return int(g.ro_query(q).result_set[0][0])

    return {
        "agents": n("MATCH (n:Agent) RETURN count(n)"), "sources": n("MATCH (n:Source) RETURN count(n)"),
        "facts": n("MATCH (n:Fact) RETURN count(n)"),
        "derived_edges": n("MATCH ()-[r:DERIVED_FROM]->() RETURN count(r)"),
        "steps": n("MATCH (n:Step) RETURN count(n)"), "reads": n("MATCH ()-[r:READ]->() RETURN count(r)"),
        "decisions": n("MATCH (n:Decision) RETURN count(n)"), "based_on": n("MATCH ()-[r:BASED_ON]->() RETURN count(r)"),
        "handoffs": n("MATCH (n:Handoff) RETURN count(n)"), "carries": n("MATCH ()-[r:CARRIES]->() RETURN count(r)"),
        "tasks": n("MATCH (n:Task) RETURN count(n)"), "depends_on": n("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r)"),
        "supersedes": n("MATCH ()-[r:SUPERSEDES]->() RETURN count(r)"),
    }  # fmt: skip


# ------------------------------------------------------------------------------------------------ files
def write_files(world: World, root: Path) -> dict[str, int]:
    """B0-style files: facts.jsonl, sources.json, decisions.jsonl, handoffs.jsonl, tasks.json, logs/<agent>.jsonl.

    The layout mirrors what a competent file-based team memory keeps: one record per line, per-agent logs of what each
    agent read, a task list. Returns the counts of what was written.
    """
    if root.exists():
        shutil.rmtree(root)
    (root / "logs").mkdir(parents=True)

    def dump(name: str, rows: list[dict[str, Any]]) -> None:
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        (root / name).write_text(text, encoding="utf-8", newline="\n")

    sup_by_new: dict[str, list[str]] = defaultdict(list)
    for n, o in world.supersedes:
        sup_by_new[n].append(o)
    dump(
        "facts.jsonl",
        [
            {"id": f["id"], "text": f["text"], "agent": f["agent"], "at": f["at"], "status": f["status"],
             "scope": f["scope"], "derived_from": f["parents"],
             **({"supersedes": sup_by_new[f["id"]]} if f["id"] in sup_by_new else {})}
            for f in world.facts
        ],
    )  # fmt: skip
    (root / "sources.json").write_text(json.dumps(world.sources), encoding="utf-8", newline="\n")
    dump(
        "decisions.jsonl",
        [{k: d[k] for k in ("id", "text", "agent", "at", "based_on")} for d in world.decisions],
    )
    dump(
        "handoffs.jsonl",
        [
            {"id": h["id"], "from": h["from"], "to": h["to"], "at": h["at"], "carries": h["carries"]}
            for h in world.handoffs
        ],
    )
    (root / "tasks.json").write_text(
        json.dumps([{"id": t["id"], "status": t["status"], "depends_on": t["deps"]} for t in world.tasks]),
        encoding="utf-8",
        newline="\n",
    )
    by_agent: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in world.steps:
        by_agent[s["agent"]].append({"step": s["id"], "n": s["n"], "at": s["at"], "read": s["reads"]})
    for a, rows in by_agent.items():
        dump(f"logs/{a}.jsonl", rows)
    return {
        "facts": len(world.facts),
        "steps": len(world.steps),
        "decisions": len(world.decisions),
        "handoffs": len(world.handoffs),
    }


def file_text_chunks(root: Path) -> list[tuple[str, str]]:
    """(file, line) records of the files, in a stable order: the unit B0r's BM25 selects over."""
    out: list[tuple[str, str]] = []
    names = ["facts.jsonl", "decisions.jsonl", "handoffs.jsonl", "sources.json", "tasks.json"]
    names += [f"logs/{p.name}" for p in sorted((root / "logs").glob("*.jsonl"))]
    for n in names:
        p = root / n
        if p.exists():
            out += [(n, ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return out
