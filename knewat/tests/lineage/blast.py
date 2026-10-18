# ruff: noqa: E501
"""A large blast radius for the ``impact`` regression tests: one Source, ``n`` derived facts in layers with
fan-in 1..3 (so paths far exceed nodes), steps that READ them, decisions / handoffs on a few, plus unrelated noise
(facts, steps and READ edges) that a scan-driven plan would have to walk.

Built on a graph with only the ``id`` range indexes (``empty_graph``, not the full schema): FalkorDB 6.0.2 inserts into the
low-cardinality ``status`` / ``predicate`` indexes of the full schema cost O(rows already indexed), so a 10,000-fact world
takes minutes there and seconds here. The ``impact`` statements only need the ``id`` indexes.
"""

from __future__ import annotations

import random
from typing import Any

from redis.exceptions import ResponseError

FAR = 9_999_999_999_999


def _w(client, graph: str, q: str, **params) -> None:
    client.graph(graph).query(q, params)


def _batches(rows: list, size: int = 1000):
    for k in range(0, len(rows), size):
        yield rows[k : k + size]


def build_blast(
    client, graph: str, *, n: int = 5000, levels: int = 12, noise: int = 5000, seed: int = 11
) -> dict[str, Any]:
    """Return ``{source, fact_ids, earliest, decisions, handoffs, agents, tasks, steps_read}``."""
    rng = random.Random(seed)
    for label in ("Source", "Fact", "Step", "Decision", "Handoff", "Task", "Agent"):
        try:
            _w(client, graph, f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        except ResponseError as exc:  # pragma: no cover - already there
            if "already indexed" not in str(exc):
                raise
    _w(
        client,
        graph,
        "CREATE (:Source {id: 'src-b', uri: 'urn:blast', kind: 'url', trust: 'normal', created_at: 1})",
    )
    _w(
        client,
        graph,
        "UNWIND range(0, 19) AS i CREATE (:Agent {id: 'ag' + toString(i), name: 'ag' + toString(i), role: 'builder'})",
    )
    _w(client, graph, "CREATE (:Task {id: 't-b', title: 'blast', status: 'pending', created_at: 1})")
    per = max(1, n // levels)
    layers: list[list[str]] = []
    facts: list[dict[str, Any]] = []
    idx = 0
    for lv in range(levels):
        count = per if lv < levels - 1 else n - per * (levels - 1)
        layer = [f"b{idx + j}" for j in range(count)]
        idx += count
        layers.append(layer)
        facts += [{"id": fid, "at": 1000 + lv * 100 + (j % 97)} for j, fid in enumerate(layer)]
    noise_facts = [{"id": f"x{i}", "at": 500 + i % 50} for i in range(noise)]
    for chunk in _batches(facts + noise_facts):
        _w(
            client,
            graph,
            "UNWIND $rows AS r CREATE (:Fact {id: r.id, predicate: 'p', value: r.id, status: 'active', "
            "valid_from: r.at, valid_to: $far, created_at: r.at})",
            rows=chunk,
            far=FAR,
        )
    edges = []
    for lv, layer in enumerate(layers):
        for j, fid in enumerate(layer):
            if lv == 0:
                edges.append({"f": fid, "t": "src-b"})
                continue
            below = layers[lv - 1]
            k = rng.choice([1, 1, 2, 2, 3])
            for t in {below[(j + s) % len(below)] for s in range(k)}:
                edges.append({"f": fid, "t": t})
    for chunk in _batches(edges):
        _w(
            client,
            graph,
            "UNWIND $e AS x MATCH (a:Fact {id: x.f}) WITH a, x OPTIONAL MATCH (b1:Fact {id: x.t}) "
            "OPTIONAL MATCH (b2:Source {id: x.t}) WITH a, coalesce(b1, b2) AS b CREATE (a)-[:DERIVED_FROM]->(b)",
            e=chunk,
        )
    # readers: every fact read by 1..2 steps of one agent (blast and noise alike)
    ids = [f["id"] for f in facts + noise_facts]
    steps = [
        {"id": f"st{i}", "n": i // 20 + 1, "agent": f"ag{i % 20}", "at": 2000 + i}
        for i in range(len(ids) * 3 // 2)
    ]
    for chunk in _batches(steps):
        _w(
            client,
            graph,
            "UNWIND $rows AS r CREATE (:Step {id: r.id, n: r.n, at: r.at, agent_id: r.agent, created_at: r.at})",
            rows=chunk,
        )
    reads = [{"s": f"st{k % len(steps)}", "f": fid} for k, fid in enumerate(ids + ids[: len(ids) // 2])]
    for chunk in _batches(reads):
        _w(
            client,
            graph,
            "UNWIND $e AS x MATCH (s:Step {id: x.s}) MATCH (f:Fact {id: x.f}) CREATE (s)-[:READ {via: 'use', at: s.at}]->(f)",
            e=chunk,
        )
    decided = [fid for fid in ids if fid.startswith("b")][:: max(1, 100 // 3)]
    handed = [fid for fid in ids if fid.startswith("b")][5 :: max(1, 100 // 2)]
    _w(
        client,
        graph,
        "UNWIND $rows AS r MATCH (f:Fact {id: r.f}), (t:Task {id: 't-b'}) "
        "CREATE (d:Decision {id: 'd-' + r.f, text: 't', at: 3000 + r.k, created_at: 3000 + r.k}), "
        "(d)-[:BASED_ON]->(f), (d)-[:FOR]->(t)",
        rows=[{"f": f, "k": k} for k, f in enumerate(decided)],
    )
    _w(
        client,
        graph,
        "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) "
        "CREATE (h:Handoff {id: 'h-' + r.f, note: 'n', at: 4000 + r.k, created_at: 4000 + r.k}), (h)-[:CARRIES]->(f)",
        rows=[{"f": f, "k": k} for k, f in enumerate(handed)],
    )
    blast = [f["id"] for f in facts]
    reads_blast = sum(1 for r in reads if r["f"].startswith("b"))
    earliest = [f["id"] for f in sorted(facts, key=lambda r: (r["at"], r["id"]))[:5]]
    return {
        "source": "src-b",
        "fact_ids": blast,
        "earliest": earliest,
        "reads_blast": reads_blast,
        "steps_blast": len({r["s"] for r in reads if r["f"].startswith("b")}),
        "decisions": sorted(f"d-{f}" for f in decided),
        "handoffs": sorted(f"h-{f}" for f in handed),
    }
