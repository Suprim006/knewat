"""Recall on a hub entity (recall-check, trials-int review item 3): the per-entity reads of
``engram/recall`` happen once per DISTINCT entity, not once per surviving row.

After p12 the candidate pool is up to 150 rows (+ keyword hits), so a hub entity contributes dozens
of rows. The merged query computed ``fan_e`` (``size([(e)<-[:ABOUT]-(:Fact {status:'active'}) |
1])``) and the sibling expansion (``OPTIONAL MATCH (e)<-[:ABOUT]-(g0:Fact)`` + one cosine distance
per hub fact + a sort) inside the per-row pipeline, so each row of the hub rescanned the hub: on a
1,000-fact hub the plan produced 61,295 records in one operator (about 60 hub rows x 1,000 facts),
on a 5,000-fact hub 305,295 (1.9 s on Docker Desktop). The fix groups the surviving rows by entity
before those reads, so the records are ``fan x distinct entities`` and do not depend on how many
rows one entity contributes.
"""

from __future__ import annotations

import math
import random

import pytest
from tests.plan_util import OPEN, max_records, profile_ops, unit_vec

SMAX = 3.912
BOOST = 0.05


def _near(rng: random.Random, q: list[float], spread: float) -> list[float]:
    v = [a + spread * b for a, b in zip(q, unit_vec(rng), strict=True)]
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _dist(a: list[float], b: list[float]) -> float:
    return 1.0 - sum(x * y for x, y in zip(a, b, strict=True))


def _seed(client, graph, hub_facts, *, small_entities=40, per_small=5, seed=11):
    """Scope ``S`` inherits ``G``; the hub ``H`` has ``hub_facts`` active facts (3 of 4 in ``S``, the rest in
    ``G``); ``small_entities`` entities with ``per_small`` facts each; 30 superseded hub facts and 30 hub
    facts in a scope that ``S`` does not inherit (``X``). Returns the query vector (= hub fact 0) and the
    fact dicts (embedding, scope, status)."""
    rng = random.Random(seed)
    q = unit_vec(rng)
    g = client.graph(graph)
    g.query(
        """CREATE (s:Scope {id: 'S', kind: 'project', name: 's', created_at: 1}),
                  (gl:Scope {id: 'G', kind: 'global', name: 'g', created_at: 1}),
                  (:Scope {id: 'X', kind: 'project', name: 'x', created_at: 1}),
                  (s)-[:INHERITS]->(gl), (:Agent {id: 'a1'})"""
    )
    ents = [{"id": "H", "name": "mega hub"}] + [
        {"id": f"E{i}", "name": f"thing {i}"} for i in range(small_entities)
    ]
    g.query("UNWIND $r AS r CREATE (:Entity {id: r.id, name: r.name})", {"r": ents})
    facts = []
    for i in range(hub_facts):
        facts.append(
            {
                "id": f"H{i}",
                "e": "H",
                "sc": "S" if i % 4 else "G",
                "st": "active",
                "emb": _near(rng, q, 0.9 + (i % 7) / 10),
            }
        )
    for i in range(30):
        facts.append({"id": f"HS{i}", "e": "H", "sc": "S", "st": "superseded", "emb": _near(rng, q, 0.3)})
    for i in range(30):
        facts.append({"id": f"HX{i}", "e": "H", "sc": "X", "st": "active", "emb": _near(rng, q, 0.3)})
    for j in range(small_entities):
        for k in range(per_small):
            facts.append(
                {"id": f"E{j}_{k}", "e": f"E{j}", "sc": "S", "st": "active", "emb": _near(rng, q, 0.8)}
            )
    facts[0]["emb"] = (
        q  # the nearest fact of the whole graph: a hub fact in scope G? i = 0 -> 'G'; fine, G is searched
    )
    for s in range(0, len(facts), 250):
        g.query(
            """UNWIND $rows AS r
               MATCH (e:Entity {id: r.e}), (sc:Scope {id: r.sc}), (a:Agent {id: 'a1'})
               CREATE (f:Fact {id: r.id, subject_id: r.e, predicate: 'p' + r.id, value: r.id,
                               norm_value: r.id,
                               value_tokens: '', valid_from: 1, valid_to: $open, recorded_at: 1,
                               created_at: 1, status: r.st, confidence: 1.0,
                               embedding: vecf32(r.emb), value_embedding: vecf32(r.emb)})
               CREATE (f)-[:ABOUT]->(e), (f)-[:IN_SCOPE]->(sc), (f)-[:ASSERTED_BY {at: 1}]->(a)""",
            {"rows": facts[s : s + 250], "open": OPEN},
        )
    return q, facts


def _params(q, **over):
    p = {
        "q": q, "scope_id": "S", "over": 240, "lim": 120, "all": False, "t": 5, "statuses": ["active"],
        "boost": BOOST, "sibs": 5, "kw_ids": [], "damp": True, "smax": SMAX,
    }  # fmt: skip
    p.update(over)
    return p


@pytest.mark.parametrize("hub_facts", [1000, 5000])
def test_hub_reads_are_per_entity_not_per_row(client, graph, hub_facts):
    q, facts = _seed(client, graph, hub_facts)
    hub_in_scope = [f["id"] for f in facts if f["e"] == "H" and f["st"] == "active" and f["sc"] in ("S", "G")]
    params = _params(q, kw_ids=hub_in_scope[:60])  # what p12's keyword channel adds: 60 + 60 rows
    ops = profile_ops(client, graph, "engram/recall", params)
    worst = max_records(ops)
    rows = client.ro(graph, "engram/recall", params)
    from_hub = sum(1 for r in rows if r["entity_id"] == "H")
    assert from_hub >= 60, (
        "the fixture must make the hub contribute dozens of rows, or this test proves nothing"
    )
    # before the fix: rows_from_hub x fan (61,295 at 1,000; 305,295 at 5,000)
    assert worst.records < 2 * hub_facts, f"per-row hub scan: {worst}\n" + "\n".join(map(str, ops))
    about = [o for o in ops if "Conditional Traverse" in o.name and "Entity" in o.args]
    assert max(o.records for o in about) < 2 * hub_facts


@pytest.mark.parametrize("allv", [False, True])
def test_hub_damp_and_siblings_match_a_python_reference(client, graph, allv):
    """The grouped query returns what the per-row form did: per seed, the nearest ``sibs`` OTHER facts of its
    entity that are active, valid and in a searched scope, ranked ``own distance - boost * damp`` (floor 0);
    ``damp`` from the entity's fan."""
    smax = 10.0  # ln(61) = 4.1: a non-zero damp for the hub as well as for the small entities
    q, facts = _seed(client, graph, 60, small_entities=6, per_small=4)
    emb = {f["id"]: f["emb"] for f in facts}
    searched = ("S", "G", "X") if allv else ("S", "G")
    eligible = {f["id"]: f for f in facts if f["st"] == "active" and f["sc"] in searched}
    fan = {}
    for f in facts:
        if f["st"] == "active":
            fan[f["e"]] = fan.get(f["e"], 0) + 1  # every scope: the entity's fan
    damp = {e: max(0.0, 1.0 - math.log(n) / smax) if n >= 1 else 1.0 for e, n in fan.items()}
    seeds = ["H3", "H7", "E2_1"]
    params = _params(q, over=1, lim=100, all=allv, smax=smax, kw_ids=seeds)
    rows = {r["fact_id"]: r for r in client.ro(graph, "engram/recall", params)}
    near = min(eligible.values(), key=lambda f: _dist(emb[f["id"]], q))["id"]  # the one vector seed
    seed_ids = set(seeds) | {near}
    expect: dict[str, float] = {}
    sib_of: dict[str, set[str]] = {}
    for s in seed_ids:
        d_s = _dist(emb[s], q)
        expect[s] = min(expect.get(s, 9.0), d_s)
        mates = sorted(
            (f for f in eligible.values() if f["e"] == eligible[s]["e"] and f["id"] != s),
            key=lambda f: _dist(emb[f["id"]], q),
        )[:5]
        for m in mates:
            d = _dist(emb[m["id"]], q)
            expect[m["id"]] = min(expect.get(m["id"], 9.0), max(0.0, d - BOOST * damp[eligible[s]["e"]]))
            sib_of.setdefault(m["id"], set()).add(s)
    assert set(rows) == set(expect)
    for fid, r in rows.items():
        assert r["rank"] == pytest.approx(expect[fid], abs=1e-4), fid
        assert r["damp"] == pytest.approx(damp[eligible[fid]["e"]], abs=1e-6), fid
        assert fid not in set(r["sib_of"]), "a fact is never its own sibling"
        assert set(r["sib_of"]) == sib_of.get(fid, set()), fid
    assert any(r["damp"] > 0 for r in rows.values()) and any(sib_of.values())
