"""Audit C3: the ``soft`` (DUPLICATES_MAYBE) list of ``engram/assert_fact`` must be cut to ``maybe_cap``
nearest-first.

Before the fix ``[sx IN keyed WHERE ...][0..$maybe_cap]`` sliced the candidates in storage order, so with
cap 1 the FARTHEST of three same-``dup_key`` facts (created far, mid, near) was kept and linked.
"""

from __future__ import annotations

import pytest
from tests.integration.test_audit_recall_hop_facts import Q, _emb
from tests.plan_util import OPEN


@pytest.fixture
def same_key(client, graph):
    g = client.graph(graph)
    g.query(
        """
        CREATE (:Scope {id:'S', kind:'project', name:'s', created_at: 1}), (:Agent {id:'a1'}),
               (:Entity {id:'E', name:'e', norm_name:'e'})
        """
    )
    rows = [  # storage order: far first
        {"id": "far", "emb": _emb(0.638)},
        {"id": "mid", "emb": _emb(0.175)},
        {"id": "near", "emb": _emb(0.005)},
    ]
    g.query(
        """
        UNWIND $rows AS r
        MATCH (e:Entity {id:'E'}), (s:Scope {id:'S'}), (a:Agent {id:'a1'})
        CREATE (f:Fact {id: r.id, subject_id: 'E', predicate: 'p', value: r.id, norm_value: r.id,
                        value_tokens: 'x',
                        dup_key: 'k', tok: ['x'], tok_seq: ['x'],
                        valid_from: 1, valid_to: $open, recorded_at: 1, created_at: 1, status: 'active',
                        confidence: 1.0, embedding: vecf32(r.emb), value_embedding: vecf32(r.emb)})
        CREATE (f)-[:ABOUT]->(e), (f)-[:IN_SCOPE]->(s), (f)-[:ASSERTED_BY {at: 1}]->(a)
        """,
        {"rows": rows, "open": OPEN},
    )
    return graph


def _assert(client, graph, cap: int, fact_id: str) -> list[dict]:
    rows = client.rw(
        graph,
        "engram/assert_fact",
        {
            "entity_id": "E",
            "predicate": "p",
            "value": "new " + fact_id,
            "norm_value": "new " + fact_id,
            "value_tokens": "x",
            "dup_key": "k",
            "tok": ["x"],
            "tok_seq": ["x"],
            "scope_id": "S",
            "agent_id": "a2",
            "source_id": "",
            "step_id": "",
            "episode_id": "",
            "confidence": 1.0,
            "supersede": False,
            "now": 5,
            "open_to": OPEN,
            "fact_id": fact_id,
            "emb": Q,
            "value_emb": Q,
            "dup_threshold": -1.0,  # tiers 1/2 off: nothing is a hard duplicate
            "jac2": 0.6,
            "cos2": 0.16,
            "maybe_cos": 0.9,
            "maybe_jac": 2.0,  # never by Jaccard: cosine decides
            "maybe_cap": cap,
            "novelty": 0.5,
            "surprise_supersede": 0.6,
            "surprise_contradict": 0.9,
        },
    )
    assert len(rows) == 1 and rows[0]["duplicate_of"] is None
    return list(rows[0]["maybe"])


def _linked(client, graph, fact_id: str) -> list[str]:
    res = client.graph(graph).ro_query(
        "MATCH (:Fact {id: $id})-[m:DUPLICATES_MAYBE]->(o:Fact) RETURN o.id ORDER BY m.cos",
        {"id": fact_id},
    )
    return [r[0] for r in res.result_set]


def test_cap_one_keeps_the_nearest_candidate(client, same_key):
    maybe = _assert(client, same_key, 1, "N1")
    assert [m["id"] for m in maybe] == ["near"], f"before C3: ['far'] (storage order); got {maybe}"
    assert _linked(client, same_key, "N1") == ["near"]


def test_cap_two_keeps_the_two_nearest_in_order(client, same_key):
    maybe = _assert(client, same_key, 2, "N2")
    assert [m["id"] for m in maybe] == ["near", "mid"]
    assert maybe[0]["cos"] < maybe[1]["cos"]
    assert _linked(client, same_key, "N2") == ["near", "mid"]


def test_no_candidates_still_writes_the_fact(client, graph):
    client.graph(graph).query(
        "CREATE (:Scope {id:'S', kind:'project', name:'s', created_at: 1}), "
        "(:Entity {id:'E', name:'e', norm_name:'e'})"
    )
    assert _assert(client, graph, 5, "N0") == []
    assert client.graph(graph).ro_query("MATCH (f:Fact {id:'N0'}) RETURN count(f)").result_set == [[1]]
