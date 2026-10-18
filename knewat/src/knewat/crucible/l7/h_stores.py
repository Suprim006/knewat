"""Family H loaders: the same :class:`HWorld` into SQLite (a normalised schema a competent author would write) and into
FalkorDB (the product model's labels and edge types). Both assert their counts against the ledger."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from knewat.crucible.l7.common import chunks
from knewat.crucible.l7.h_world import HWorld

SQL_SCHEMA = """
CREATE TABLE agents(id TEXT PRIMARY KEY);
CREATE TABLE sources(id TEXT PRIMARY KEY);
CREATE TABLE facts(id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL, status TEXT NOT NULL,
                   agent_id TEXT NOT NULL REFERENCES agents(id), at INTEGER NOT NULL);
CREATE TABLE fact_parent(child TEXT NOT NULL, parent TEXT NOT NULL, PRIMARY KEY(child, parent)) WITHOUT ROWID;
CREATE TABLE fact_source(fact_id TEXT PRIMARY KEY, source_id TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE steps(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, at INTEGER NOT NULL);
CREATE TABLE step_reads(step_id TEXT NOT NULL, fact_id TEXT NOT NULL, PRIMARY KEY(step_id, fact_id)) WITHOUT ROWID;
CREATE TABLE decisions(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, at INTEGER NOT NULL);
CREATE TABLE decision_based_on(decision_id TEXT NOT NULL, fact_id TEXT NOT NULL,
                               PRIMARY KEY(decision_id, fact_id)) WITHOUT ROWID;
CREATE TABLE handoffs(id TEXT PRIMARY KEY, from_agent TEXT NOT NULL, to_agent TEXT NOT NULL, at INTEGER NOT NULL);
CREATE TABLE handoff_carries(handoff_id TEXT NOT NULL, fact_id TEXT NOT NULL,
                             PRIMARY KEY(handoff_id, fact_id)) WITHOUT ROWID;
"""
# The indexes a competent author adds for these questions (reported with the results).
SQL_INDEXES = (
    "CREATE INDEX fact_parent_parent ON fact_parent(parent, child)",
    "CREATE INDEX fact_source_source ON fact_source(source_id, fact_id)",
    "CREATE INDEX facts_subject ON facts(subject, predicate)",
    "CREATE INDEX steps_agent ON steps(agent_id, at)",
    "CREATE INDEX step_reads_fact ON step_reads(fact_id)",
    "CREATE INDEX decisions_agent ON decisions(agent_id)",
    "CREATE INDEX dbo_fact ON decision_based_on(fact_id)",
    "CREATE INDEX handoffs_from ON handoffs(from_agent)",
    "CREATE INDEX handoffs_to ON handoffs(to_agent)",
    "CREATE INDEX hc_fact ON handoff_carries(fact_id)",
)
# FalkorDB: a range index on `id` for every label, plus Fact(subject) and Fact(status).
CYPHER_INDEXES = tuple(
    f"CREATE INDEX FOR (n:{lb}) ON (n.id)"
    for lb in ("Agent", "Source", "Fact", "Step", "Decision", "Handoff")
) + ("CREATE INDEX FOR (n:Fact) ON (n.subject)", "CREATE INDEX FOR (n:Fact) ON (n.status)")


def _check(world: HWorld, got: dict[str, int], arm: str) -> None:
    want = world.counts()
    bad = {k: (want[k], got[k]) for k in want if got.get(k) != want[k]}
    if bad:
        raise AssertionError(f"{arm}: store differs from the ledger (ledger, store): {bad}")


def build_sqlite(world: HWorld, path: Path) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)
    c = sqlite3.connect(path, isolation_level=None)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=OFF")
    c.executescript(SQL_SCHEMA)
    c.execute("BEGIN")
    c.executemany("INSERT INTO agents VALUES(?)", [(a,) for a in world.agents])
    c.executemany("INSERT INTO sources VALUES(?)", [(s,) for s in world.sources])
    c.executemany(
        "INSERT INTO facts VALUES(?,?,?,?,?,?)",
        [(f["id"], f["subject"], f["predicate"], f["status"], f["agent"], f["at"]) for f in world.facts],
    )
    c.executemany("INSERT INTO fact_parent VALUES(?,?)", world.fact_parents)
    c.executemany("INSERT INTO fact_source VALUES(?,?)", world.fact_source)
    c.executemany("INSERT INTO steps VALUES(?,?,?)", [(s["id"], s["agent"], s["at"]) for s in world.steps])
    c.executemany(
        "INSERT INTO step_reads VALUES(?,?)", [(s["id"], f) for s in world.steps for f in s["reads"]]
    )
    c.executemany(
        "INSERT INTO decisions VALUES(?,?,?)", [(d["id"], d["agent"], d["at"]) for d in world.decisions]
    )
    c.executemany(
        "INSERT INTO decision_based_on VALUES(?,?)",
        [(d["id"], f) for d in world.decisions for f in d["based_on"]],
    )
    c.executemany(
        "INSERT INTO handoffs VALUES(?,?,?,?)",
        [(h["id"], h["from"], h["to"], h["at"]) for h in world.handoffs],
    )
    c.executemany(
        "INSERT INTO handoff_carries VALUES(?,?)",
        [(h["id"], f) for h in world.handoffs for f in h["carries"]],
    )
    c.execute("COMMIT")
    for ddl in SQL_INDEXES:
        c.execute(ddl)
    c.execute("ANALYZE")
    c.execute("PRAGMA synchronous=NORMAL")

    def n(t: str) -> int:
        return int(c.execute(f"SELECT count(*) FROM {t}").fetchone()[0])

    got = {
        "agents": n("agents"), "sources": n("sources"), "facts": n("facts"), "fact_parents": n("fact_parent"),
        "fact_source": n("fact_source"), "steps": n("steps"), "reads": n("step_reads"), "decisions": n("decisions"),
        "based_on": n("decision_based_on"), "handoffs": n("handoffs"), "carries": n("handoff_carries"),
    }  # fmt: skip
    c.close()
    _check(world, got, "SQLite")
    return got


def load_falkordb(world: HWorld, g: Any) -> dict[str, int]:
    """Load into the (empty) falkordb ``Graph`` ``g`` with the product model's labels and relationship types."""
    for ddl in CYPHER_INDEXES:
        g.query(ddl)

    def run(cypher: str, rows: list[Any]) -> None:
        for ch in chunks(rows):
            g.query(cypher, {"rows": ch})

    run("UNWIND $rows AS r CREATE (:Agent {id: r})", world.agents)
    run("UNWIND $rows AS r CREATE (:Source {id: r})", world.sources)
    run(
        "UNWIND $rows AS r MATCH (a:Agent {id: r.agent}) "
        "CREATE (f:Fact {id: r.id, subject: r.subject, predicate: r.predicate, status: r.status, at: r.at})"
        "-[:ASSERTED_BY]->(a)",
        world.facts,
    )
    run(
        "UNWIND $rows AS r MATCH (c:Fact {id: r[0]}) MATCH (p:Fact {id: r[1]}) CREATE (c)-[:DERIVED_FROM]->(p)",
        [list(e) for e in world.fact_parents],
    )
    run(
        "UNWIND $rows AS r MATCH (f:Fact {id: r[0]}) MATCH (s:Source {id: r[1]}) CREATE (f)-[:DERIVED_FROM]->(s)",
        [list(e) for e in world.fact_source],
    )
    run(
        "UNWIND $rows AS r MATCH (a:Agent {id: r.agent}) CREATE (:Step {id: r.id, at: r.at})-[:BY]->(a)",
        world.steps,
    )
    run(
        "UNWIND $rows AS r MATCH (s:Step {id: r[0]}) MATCH (f:Fact {id: r[1]}) CREATE (s)-[:READ]->(f)",
        [[s["id"], f] for s in world.steps for f in s["reads"]],
    )
    run(
        "UNWIND $rows AS r MATCH (a:Agent {id: r.agent}) CREATE (a)-[:DECIDED]->(:Decision {id: r.id, at: r.at})",
        world.decisions,
    )
    run(
        "UNWIND $rows AS r MATCH (d:Decision {id: r[0]}) MATCH (f:Fact {id: r[1]}) CREATE (d)-[:BASED_ON]->(f)",
        [[d["id"], f] for d in world.decisions for f in d["based_on"]],
    )
    run(
        "UNWIND $rows AS r MATCH (x:Agent {id: r.from}) MATCH (y:Agent {id: r.to}) "
        "CREATE (x)<-[:FROM]-(:Handoff {id: r.id, at: r.at})-[:TO]->(y)",
        world.handoffs,
    )
    run(
        "UNWIND $rows AS r MATCH (h:Handoff {id: r[0]}) MATCH (f:Fact {id: r[1]}) CREATE (h)-[:CARRIES]->(f)",
        [[h["id"], f] for h in world.handoffs for f in h["carries"]],
    )

    def n(q: str) -> int:
        return int(g.ro_query(q).result_set[0][0])

    got = {
        "agents": n("MATCH (x:Agent) RETURN count(x)"), "sources": n("MATCH (x:Source) RETURN count(x)"),
        "facts": n("MATCH (x:Fact) RETURN count(x)"),
        "fact_parents": n("MATCH (:Fact)-[r:DERIVED_FROM]->(:Fact) RETURN count(r)"),
        "fact_source": n("MATCH (:Fact)-[r:DERIVED_FROM]->(:Source) RETURN count(r)"),
        "steps": n("MATCH (x:Step) RETURN count(x)"), "reads": n("MATCH ()-[r:READ]->() RETURN count(r)"),
        "decisions": n("MATCH (x:Decision) RETURN count(x)"), "based_on": n("MATCH ()-[r:BASED_ON]->() RETURN count(r)"),
        "handoffs": n("MATCH (x:Handoff) RETURN count(x)"), "carries": n("MATCH ()-[r:CARRIES]->() RETURN count(r)"),
    }  # fmt: skip
    _check(world, got, "FalkorDB")
    return got
