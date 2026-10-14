"""Helpers for plan-shape tests: run a named query under GRAPH.PROFILE and look at what each operation produced.

A scope-first plan (start at the Scope, enumerate every fact IN_SCOPE, filter afterwards) shows up as one
operation producing ~"facts in the scope" records. An entity- or source-anchored plan only touches the rows
that belong to the entity / source. Asserting on ``max_records`` therefore catches the regression without
depending on operator names or aliases.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from plexus.graph.client import GraphClient
from plexus.graph.queries import QueryLibrary


@dataclass(frozen=True)
class Op:
    name: str
    args: str
    records: int

    def __str__(self) -> str:
        return f"{self.name} | {self.args} | {self.records} records"


def _walk(op, out: list[Op]) -> None:
    stats = getattr(op, "profile_stats", None)
    out.append(Op(op.name, str(op.args or ""), stats.records_produced if stats else 0))
    for child in op.children:
        _walk(child, out)


def profile_ops(client: GraphClient, graph: str, query: str, params: dict[str, Any]) -> list[Op]:
    """GRAPH.PROFILE a named query (single statement; a write query really runs, use a throw-away graph)."""
    lib: QueryLibrary = client.library
    q = lib.get(query)
    assert len(q.statements) == 1
    plan = client.graph(graph).profile(q.statements[0], params)
    ops: list[Op] = []
    _walk(plan.structured_plan, ops)
    return ops


def explain_lines(client: GraphClient, graph: str, query: str, params: dict[str, Any]) -> list[str]:
    q = client.library.get(query)
    plan = client.graph(graph).explain(q.statements[0], params)
    return [line.strip() for line in plan.plan]


def max_records(ops: list[Op]) -> Op:
    return max(ops, key=lambda o: o.records)


def unit_vec(rng: random.Random, dim: int = 384) -> list[float]:
    v = [rng.gauss(0, 1) for _ in range(dim)]
    norm = sum(x * x for x in v) ** 0.5
    return [x / norm for x in v]


OPEN = 9_999_999_999_999
BIG = 400  # facts in the scope: far more than any entity or source fan-out used by the tests
PER_ENTITY = 5


def seed_big_scope(
    client: GraphClient, graph: str, *, status: str = "active", n_facts: int = BIG, seed: int = 7
) -> dict[str, Any]:
    """One scope with ``n_facts`` facts spread over ``n_facts / 5`` entities (5 each), predicate ``p``.

    Entity ``E0`` owns facts ``F0..F4``. Source ``SRC`` has two facts derived from it (``F0`` directly, ``F1``
    through ``F0``); Source ``SRC_EMPTY`` has none. All facts carry random unit embeddings.
    """
    rng = random.Random(seed)
    g = client.graph(graph)
    g.query("CREATE (:Scope {id: 'S', kind: 'project', name: 'big', created_at: 1}), (:Agent {id: 'a1'})")
    g.query(
        "UNWIND range(0, $n - 1) AS i CREATE (:Entity {id: 'E' + toString(i), name: 'e' + toString(i)})",
        {"n": n_facts // PER_ENTITY},
    )
    batch = 100
    for start in range(0, n_facts, batch):
        rows = [
            {"i": i, "e": f"E{i // PER_ENTITY}", "emb": unit_vec(rng)}
            for i in range(start, min(start + batch, n_facts))
        ]
        g.query(
            """UNWIND $rows AS r
               MATCH (e:Entity {id: r.e}), (s:Scope {id: 'S'}), (a:Agent {id: 'a1'})
               CREATE (f:Fact {id: 'F' + toString(r.i), subject_id: r.e, predicate: 'p', value: 'v' + toString(r.i),
                               norm_value: 'v' + toString(r.i), value_tokens: '', valid_from: 1, valid_to: $open,
                               recorded_at: 1, created_at: 1, status: $status, confidence: 1.0,
                               embedding: vecf32(r.emb), value_embedding: vecf32(r.emb)})
               CREATE (f)-[:ABOUT]->(e), (f)-[:IN_SCOPE]->(s), (f)-[:ASSERTED_BY {at: 1}]->(a)""",
            {"rows": rows, "open": OPEN, "status": status},
        )
    g.query(
        """CREATE (:Source {id: 'SRC', uri: 'u:src', kind: 'doc', created_at: 1}),
                  (:Source {id: 'SRC_EMPTY', uri: 'u:empty', kind: 'doc', created_at: 1})"""
    )
    g.query(
        """MATCH (s:Source {id: 'SRC'}), (f0:Fact {id: 'F0'}), (f1:Fact {id: 'F1'})
           CREATE (f0)-[:DERIVED_FROM]->(s), (f1)-[:DERIVED_FROM]->(f0)"""
    )
    return {"rng": rng, "n_facts": n_facts}


def seed_steps(client: GraphClient, graph: str, n_steps: int = BIG, agents: int = 20) -> None:
    """``n_steps`` Steps spread over ``agents`` agents (``ag0``..), numbered 1.. per agent."""
    client.graph(graph).query(
        """UNWIND range(0, $n - 1) AS i
           CREATE (:Step {id: 'ST' + toString(i), n: i / $agents + 1, at: i, agent_id: 'ag' + toString(i % $agents),
                          created_at: 1})""",
        {"n": n_steps, "agents": agents},
    )
