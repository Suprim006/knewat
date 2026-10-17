"""P5-fix: plan-shape regressions for review findings Q1-Q3.

Queries must follow the entity / source, not enumerate every fact of the scope. Each test seeds a
throw-away graph with 400 facts in ONE scope (5 per entity) and profiles the query: no operation may
produce as many records as the scope has facts.
"""

from __future__ import annotations

import pytest
from tests.plan_util import BIG, max_records, profile_ops, seed_big_scope

from plexus.engram.service import OPEN


@pytest.fixture
def big(client, graph):
    return seed_big_scope(client, graph)


def _assert_small(ops, limit=BIG):
    worst = max_records(ops)
    assert worst.records < limit, f"scope-wide enumeration: {worst}\n" + "\n".join(map(str, ops))


# -- Q1: recall's sibling expansion must be entity-first ----------------------------------------------


def test_q1_recall_sibling_expansion_does_not_enumerate_the_scope(client, graph, big):
    vec = client.graph(graph).ro_query("MATCH (f:Fact {id: 'F0'}) RETURN f.embedding").result_set[0][0]
    params = {
        "q": list(vec),
        "scope_id": "S",
        "over": 32,
        "k": 8,
        "t": 5,
        "statuses": ["active"],
        "boost": 0.05,
        "sibs": 5,
        "kw_ids": [],
        "damp": True,
        "smax": 3.912,
    }
    ops = profile_ops(client, graph, "engram/recall", params)
    _assert_small(ops)


# -- Q2: assert_fact / fact_history must start at the entity ------------------------------------------


def _assert_params(**over):
    p = {
        "entity_id": "E0",
        "predicate": "p",
        "value": "brand new",
        "norm_value": "brand new",
        "value_tokens": "",
        "dup_key": "",
        "tok": ["brand", "new"],
        "tok_seq": ["brand", "new"],
        "scope_id": "S",
        "agent_id": "a2",
        "source_id": "",
        "step_id": "",
        "episode_id": "",
        "confidence": 1.0,
        "supersede": False,
        "now": 5,
        "open_to": OPEN,
        "fact_id": "NEW",
        "emb": [0.05] * 384,
        "value_emb": [0.05] * 384,
        "dup_threshold": 0.08,
        "jac2": 0.6,
        "cos2": 0.16,
        "maybe_cos": 0.2,
        "maybe_jac": 0.5,
        "maybe_cap": 5,
        "novelty": 0.5,
        "surprise_supersede": 0.6,
        "surprise_contradict": 0.9,
    }
    p.update(over)
    return p


def test_q2_assert_fact_current_lookup_does_not_enumerate_the_scope(client, graph, big):
    ops = profile_ops(client, graph, "engram/assert_fact", _assert_params())
    _assert_small(ops)
    # the lookup still finds the five current facts of E0 (another agent, no supersede: they all clash)
    q = "MATCH (:Fact {id: 'NEW'})-[:CONTRADICTS]->(o:Fact) RETURN count(o)"
    assert client.graph(graph).ro_query(q).result_set[0][0] == 5


def test_q2_fact_history_does_not_enumerate_the_scope(client, graph, big):
    ops = profile_ops(
        client,
        graph,
        "engram/fact_history",
        {"entity_id": "E0", "predicate": "p", "scope_id": "S", "limit": 50},
    )
    _assert_small(ops)


# -- Q3: the DERIVED_FROM cascade must be anchored at the Source -------------------------------------


@pytest.mark.parametrize("query", ["lineage/forget_source", "lineage/quarantine"])
def test_q3_cascade_from_a_source_with_no_facts_touches_no_facts(client, graph, big, query):
    params = {"source_id": "SRC_EMPTY", "now": 5, "limit": 5000, "max_detail": 100, "depth": 12}
    if query == "lineage/forget_source":
        params["reason"] = "r"
    ops = profile_ops(client, graph, query, params)
    _assert_small(ops, limit=20)


def test_q3_release_quarantine_is_not_proportional_to_quarantined_facts(client, graph):
    seed_big_scope(client, graph, status="quarantined")
    ops = profile_ops(
        client, graph, "lineage/release_quarantine", {"source_id": "SRC_EMPTY", "limit": 5000, "depth": 12}
    )
    _assert_small(ops, limit=20)


def test_q3_cascade_follows_chains_from_the_source(client, graph, big):
    ops = profile_ops(
        client,
        graph,
        "lineage/quarantine",
        {"source_id": "SRC", "now": 5, "limit": 5000, "max_detail": 100, "depth": 12},
    )
    _assert_small(ops, limit=20)
