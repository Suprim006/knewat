"""A large synthetic blast radius for the P9-f ``impact`` tests: one Source, ``n`` facts in ``levels`` layers.

Shaped like Crucible L6 family A's 5,000-fact question. Layer 1 derives from the Source; a fact of layer
k >= 2 derives from 1, 2 or 3 facts of layer k-1 (a diamond lineage: many more paths than nodes). Every fact
is READ by 0-3 Steps of 50 agents; about 3% have a Decision ``BASED_ON`` them (each FOR one of 5 tasks) and
2% a Handoff that ``CARRIES`` them. Every fact has a distinct ``created_at`` / ``valid_from``, shuffled
against the layers, so "the earliest N" has one answer that the layer order does not give away.

Built with raw parameterised Cypher in batches of 200 (not the services): 5,000 facts load in ~15 s. Seeded.
"""

from __future__ import annotations

import random
from typing import Any

FAR = 9_999_999_999_999
T0 = 1_700_000_000_000
SOURCE = "src-blast"

Q = {
    "agents": "UNWIND $rows AS r CREATE (:Agent {id: r.id, name: r.id, role: 'worker'})",
    "tasks": "UNWIND $rows AS r CREATE (:Task {id: r.id, title: r.id, status: 'open', version: 1})",
    "facts": "UNWIND $rows AS r CREATE (:Fact {id: r.id, predicate: 'p', value: r.id, status: 'active', "
    "valid_from: r.at, valid_to: $far, recorded_at: r.at, created_at: r.at})",
    "from_source": "UNWIND $rows AS x MATCH (a:Fact {id: x.f}) MATCH (b:Source {id: x.t}) "
    "CREATE (a)-[:DERIVED_FROM]->(b)",
    "from_fact": "UNWIND $rows AS x MATCH (a:Fact {id: x.f}) MATCH (b:Fact {id: x.t}) "
    "CREATE (a)-[:DERIVED_FROM]->(b)",
    "steps": "UNWIND $rows AS r "
    "CREATE (:Step {id: r.id, agent_id: r.agent, n: r.n, at: r.at, created_at: r.at})",
    "reads": "UNWIND $rows AS x MATCH (s:Step {id: x.s}) MATCH (f:Fact {id: x.f}) "
    "CREATE (s)-[:READ {via: 'use', at: 1}]->(f)",
    "decisions": "UNWIND $rows AS r MATCH (t:Task {id: r.task}) "
    "CREATE (d:Decision {id: r.id, text: 'd', at: r.at, created_at: r.at}) CREATE (d)-[:FOR]->(t)",
    "based": "UNWIND $rows AS x MATCH (d:Decision {id: x.d}) MATCH (f:Fact {id: x.f}) "
    "CREATE (d)-[:BASED_ON]->(f)",
    "handoffs": "UNWIND $rows AS r CREATE (:Handoff {id: r.id, note: 'h', at: r.at, created_at: r.at})",
    "carries": "UNWIND $rows AS x MATCH (h:Handoff {id: x.h}) MATCH (f:Fact {id: x.f}) "
    "CREATE (h)-[:CARRIES]->(f)",
}


def _load(client, graph: str, name: str, rows: list[dict[str, Any]], size: int = 200) -> None:
    """Batches of 200: one UNWIND of 2,000 new Facts took > 5 s here (index upkeep grows with the batch)."""
    for i in range(0, len(rows), size):
        client.graph(graph).query(Q[name], {"rows": rows[i : i + size], "far": FAR})


def _lineage(rng: random.Random, n: int, levels: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    per = max(1, n // levels)
    order = list(range(n))
    rng.shuffle(order)
    facts: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    below: list[str] = []
    for lv in range(levels):
        size = per if lv < levels - 1 else n - per * (levels - 1)
        layer = []
        for _ in range(size):
            k = len(facts)
            fid = f"bf{k:05d}"
            facts.append({"id": fid, "at": T0 + order[k]})
            parents = [SOURCE] if lv == 0 else rng.sample(below, min(len(below), rng.choice((1, 1, 2, 2, 3))))
            edges += [{"f": fid, "t": p} for p in parents]
            layer.append(fid)
        below = layer
    return facts, edges


def build_blast(
    client, graph: str, *, n: int = 5000, levels: int = 12, seed: int = 20261016
) -> dict[str, Any]:
    """Load the blast; return the answer: ``{source, facts (by created_at), at, agents, steps, ...}``."""
    rng = random.Random(seed)
    client.graph(graph).query(
        f"CREATE (:Source {{id: '{SOURCE}', uri: 'urn:blast', kind: 'url', created_at: 1}})"
    )
    agents = [f"ag{i:02d}" for i in range(50)]
    tasks = [f"tk{i}" for i in range(5)]
    _load(client, graph, "agents", [{"id": a} for a in agents])
    _load(client, graph, "tasks", [{"id": t} for t in tasks])
    facts, edges = _lineage(rng, n, levels)
    _load(client, graph, "facts", facts)
    _load(client, graph, "from_source", [e for e in edges if e["t"] == SOURCE])
    _load(client, graph, "from_fact", [e for e in edges if e["t"] != SOURCE])
    steps, reads = [], []
    for f in facts:
        for _ in range(rng.choice((0, 1, 1, 2, 3))):
            sid = f"st{len(steps):06d}"
            steps.append({"id": sid, "agent": rng.choice(agents), "n": len(steps), "at": f["at"] + 1})
            reads.append({"s": sid, "f": f["id"]})
    _load(client, graph, "steps", steps)
    _load(client, graph, "reads", reads)
    decisions, handoffs, based, carries = [], [], [], []
    for f in facts:
        r = rng.random()
        if r < 0.03:
            did = f"dc{len(decisions):05d}"
            decisions.append({"id": did, "task": rng.choice(tasks), "at": f["at"] + 2})
            based.append({"d": did, "f": f["id"]})
        elif r < 0.05:
            hid = f"ho{len(handoffs):05d}"
            handoffs.append({"id": hid, "at": f["at"] + 3})
            carries.append({"h": hid, "f": f["id"]})
    for name, rows in (
        ("decisions", decisions),
        ("based", based),
        ("handoffs", handoffs),
        ("carries", carries),
    ):
        _load(client, graph, name, rows)
    return {
        "source": SOURCE,
        "facts": [f["id"] for f in sorted(facts, key=lambda f: f["at"])],
        "at": {f["id"]: f["at"] for f in facts},
        "agents": sorted({s["agent"] for s in steps}),
        "steps": len(steps),
        "decisions": sorted(d["id"] for d in decisions),
        "tasks": sorted({d["task"] for d in decisions}),
        "handoffs": sorted(h["id"] for h in handoffs),
    }
