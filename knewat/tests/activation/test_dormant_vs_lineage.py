"""P7-int: a dormant fact is still a fact: forget and quarantine reach it, restore cannot revive it."""

from __future__ import annotations

import pytest

from knewat.activation import Activation, Settings
from knewat.activation.model import DAY_MS

from .conftest import cypher, write

NOW = 5_000 * DAY_MS
OLD = NOW - 400 * DAY_MS


@pytest.fixture
def act(client, graph) -> Activation:
    return Activation(client, graph, Settings(), clock=lambda: NOW)


def status(client, graph, fid):
    return cypher(client, graph, "MATCH (f:Fact {id:$f}) RETURN f.status", f=fid)[0][0]


@pytest.fixture
def dormant_from_source(act, eng, lin, scope):
    """A source, a fact derived from it, and that fact swept to dormant."""
    src = lin.create_source("https://docs.example/x", kind="doc", now=1)
    f = eng.assert_fact("Thing doc", "note", "from a doc", scope, "alice", source_id=src, now=OLD)["fact_id"]
    assert act.apply_sweep([f], NOW) == [f]
    return src, f


def test_forgetting_a_source_forgets_its_dormant_facts_and_restore_cannot_revive_them(
    dormant_from_source, act, lin, client, graph
):
    src, f = dormant_from_source
    out = lin.forget_source(src)
    assert out["fact_ids"] == [f]
    assert status(client, graph, f) == "forgotten"
    assert act.restore(f) == {"fact_id": f, "restored": False, "status": "forgotten", "was": "forgotten"}
    assert status(client, graph, f) == "forgotten"


def test_quarantining_a_source_isolates_its_dormant_facts_and_releasing_puts_them_back_to_dormant(
    dormant_from_source, act, lin, client, graph
):
    src, f = dormant_from_source
    assert lin.quarantine(src)["fact_ids"] == [f]
    assert status(client, graph, f) == "quarantined"
    assert act.restore(f)["restored"] is False and status(client, graph, f) == "quarantined"
    assert lin.release_quarantine(src)["fact_ids"] == [f]
    assert status(client, graph, f) == "dormant", "released to what it was: still swept"
    assert act.restore(f)["restored"] is True and status(client, graph, f) == "active"


def test_restore_refuses_a_dormant_fact_derived_from_a_forgotten_fact(act, eng, lin, scope, client, graph):
    """Data from before this rule: a dormant fact whose parent was forgotten must stay dormant."""
    parent = eng.assert_fact("Thing p", "note", "parent", scope, "alice", now=OLD)["fact_id"]
    child = eng.assert_fact("Thing c", "note", "child", scope, "alice", now=OLD)["fact_id"]
    write(
        client,
        graph,
        "MATCH (c:Fact {id:$c}), (p:Fact {id:$p}) CREATE (c)-[:DERIVED_FROM]->(p) "
        "SET c.status = 'dormant', c.prior_status = 'active', c.dormant_at = 1, p.status = 'forgotten'",
        c=child,
        p=parent,
    )
    r = act.restore(child)
    assert r is not None and r["restored"] is False and r["status"] == "dormant"
    write(client, graph, "MATCH (p:Fact {id:$p}) SET p.status = 'active'", p=parent)
    assert act.restore(child)["restored"] is True and status(client, graph, child) == "active"
