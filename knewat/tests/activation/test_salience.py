"""D-013 P2: graded salience from the graph (every input fires once), the pin cache, and the sweep margin."""

from __future__ import annotations

import math

import pytest

from knewat.activation import Activation, Settings
from knewat.activation.service import SALIENCE_W, salience_of

from .conftest import DAY, write

NOW = 10_000

FIX = """
CREATE (e:Entity {id:'e1', name:'Thing', norm_name:'thing'})
CREATE (sc:Scope {id:'global', name:'global', kind:'global'})
CREATE (f:Fact {id:'f1', status:'active', created_at: 1000, predicate:'p', value:'v', pinned: true,
                valid_from: 1000, valid_to: 9999999999999})
CREATE (f2:Fact {id:'f2', status:'active', created_at: 1000, predicate:'p', value:'v2',
                 valid_from: 1000, valid_to: 9999999999999})
CREATE (f)-[:ABOUT]->(e), (f2)-[:ABOUT]->(e), (f)-[:IN_SCOPE]->(sc), (f2)-[:IN_SCOPE]->(sc)
CREATE (a1:Agent {id:'a1'}), (a2:Agent {id:'a2'}), (a3:Agent {id:'a3'})
CREATE (f)-[:ASSERTED_BY {at: 1000}]->(a1)
CREATE (t1:Task {id:'t1', status:'done'}), (t2:Task {id:'t2', status:'open'})
CREATE (d1:Decision {id:'d1', created_at: 3000})-[:BASED_ON]->(f)
CREATE (d2:Decision {id:'d2', created_at: 3500, flagged: true})-[:BASED_ON]->(f)
CREATE (d1)-[:FOR]->(t1), (d2)-[:FOR]->(t2)
CREATE (ar1:Artifact {id:'ar1'})-[:FOR]->(t1)
CREATE (ar2:Artifact {id:'ar2'})-[:FOR]->(t1)
CREATE (ar1)-[:VERIFIED_BY {at: 4000, independent: true}]->(a3)
CREATE (ar2)-[:VERIFIED_BY {at: 4000, independent: false}]->(a1)
CREATE (h:Handoff {id:'h1', created_at: 5000})-[:CARRIES]->(f)
CREATE (f)-[:VERIFIED_BY {at: 6000, outcome:'confirmed'}]->(a2)
CREATE (src:Source {id:'s1', trust:'high'})
CREATE (f)-[:DERIVED_FROM]->(src)
CREATE (s1:Step {id:'st1', agent_id:'a1', at: 7000}), (s2:Step {id:'st2', agent_id:'a2', at: 7100}),
       (s3:Step {id:'st3', agent_id:'a3', at: 7200})
CREATE (s1)-[:READ {via:'use', at: 7000, suspect: false}]->(f)
CREATE (s2)-[:READ {via:'use', at: 7100, suspect: false}]->(f)
CREATE (s3)-[:READ {via:'recall', at: 7200, suspect: false}]->(f)
CREATE (s3)-[:READ {via:'use', at: 99999999, suspect: false}]->(f)
"""


@pytest.fixture
def world(client, graph):
    write(client, graph, FIX)
    return client, graph


def test_every_salience_input_is_read_and_weighted(world):
    client, graph = world
    row = client.ro(graph, "activation/activation", {"fact_ids": ["f1", "f2"], "now": NOW, "events": 50})
    by = {r["id"]: r for r in row}
    s, inputs = salience_of(by["f1"], NOW)
    assert inputs == {
        "decisions": 1,  # d2 is flagged
        "verified": 1,
        "artifacts_ok": 1,  # ar2 is not independent
        "tasks_done": 1,  # t2 is open
        "use_agents": 1,  # a1 and a2 used it (the recall by a3 and the future use do not count): 2 - 1
        "handoffs": 1,
        "trusted_source": 1,
        "pinned": 1,
    }
    total = sum(SALIENCE_W[k] * v for k, v in inputs.items())
    assert s == pytest.approx(1 - math.exp(-total)) and s > 0.99
    assert salience_of(by["f2"], NOW) == (0.0, dict.fromkeys(inputs, 0))
    # events after `now` do not count
    s_early, early = salience_of(by["f1"], 2000)
    assert early["decisions"] == early["verified"] == early["handoffs"] == early["use_agents"] == 0
    assert early["pinned"] == early["trusted_source"] == 1
    assert s_early == pytest.approx(1 - math.exp(-4.0))


def test_artifacts_ok_counts_distinct_verified_artifacts_of_done_tasks_only(world):
    """Audit C1: one artifact verified twice on a done task + one artifact on an open task = 1, not 3."""
    client, graph = world
    write(
        client,
        graph,
        """
        MATCH (f:Fact {id:'f2'}), (a1:Agent {id:'a1'}), (a2:Agent {id:'a2'}), (a3:Agent {id:'a3'})
        CREATE (td:Task {id:'td', status:'done'}), (to:Task {id:'to', status:'open'})
        CREATE (d:Decision {id:'d3', created_at: 3000})-[:BASED_ON]->(f)
        CREATE (d)-[:FOR]->(td), (d)-[:FOR]->(to)
        CREATE (x1:Artifact {id:'x1'})-[:FOR]->(td)
        CREATE (x1)-[:VERIFIED_BY {at: 4000, independent: true}]->(a2)
        CREATE (x1)-[:VERIFIED_BY {at: 4100, independent: true}]->(a3)
        CREATE (x2:Artifact {id:'x2'})-[:FOR]->(to)
        CREATE (x2)-[:VERIFIED_BY {at: 4000, independent: true}]->(a1)
        """,
    )
    (row,) = client.ro(graph, "activation/activation", {"fact_ids": ["f2"], "now": NOW, "events": 50})
    (d,) = row["decisions"]
    assert d["tasks_done"] == 1
    assert sorted(d["verified_artifacts"]) == ["x1", "x1"], "one id per VERIFIED_BY path, open task excluded"
    s, inputs = salience_of(row, NOW)
    assert inputs["artifacts_ok"] == 1, "distinct artifacts: x1 once (x2 is on an open task)"
    assert inputs["decisions"] == 1 and inputs["tasks_done"] == 1
    assert s == pytest.approx(1 - math.exp(-(1.0 + 1.0 + 0.5)))


def test_salience_alone_does_not_protect(world):
    client, graph = world
    # a fact used by two agents and verified once, with no boolean protection rule
    write(
        client,
        graph,
        """
        MATCH (sc:Scope {id:'global'}), (e:Entity {id:'e1'}), (a2:Agent {id:'a2'})
        CREATE (g:Fact {id:'g1', status:'active', created_at: 1000, predicate:'q', value:'w',
                        valid_from: 1000, valid_to: 9999999999999})-[:ABOUT]->(e)
        CREATE (g)-[:IN_SCOPE]->(sc)
        CREATE (g)-[:VERIFIED_BY {at: 6000, outcome:'confirmed'}]->(a2)
        CREATE (x1:Step {id:'sx1', agent_id:'a1', at: 7000})-[:READ {via:'use', at: 7000}]->(g)
        CREATE (x2:Step {id:'sx2', agent_id:'a2', at: 7100})-[:READ {via:'use', at: 7100}]->(g)
        """,
    )
    act = Activation(client, graph, Settings(), clock=lambda: NOW)
    fa = act.compute(["g1"])["g1"]
    assert fa.salience == pytest.approx(1 - math.exp(-2.0))  # 1.5 verified + 0.5 (2 agents - 1)
    # D-013 amendment 2: salience is reported, the D-012 boolean rules alone protect
    assert not fa.protected and fa.protect_reasons == []
    # the sweep threshold is A0 - 2 (D-012)
    assert act.sweep("global", now=NOW)["threshold"] == pytest.approx(act.settings.neutral - 2.0)


def test_salience_inputs_leave_the_d012_rules_alone(world):
    """A fact protected by none of D-012's rules stays unprotected whatever its salience; the D-012 boolean
    rules still protect."""
    client, graph = world
    write(
        client,
        graph,
        """
        MATCH (sc:Scope {id:'global'}), (e:Entity {id:'e1'}),
              (a1:Agent {id:'a1'}), (a2:Agent {id:'a2'}), (a3:Agent {id:'a3'})
        CREATE (g:Fact {id:'g2', status:'active', created_at: 1000, predicate:'q', value:'w2',
                        valid_from: 1000, valid_to: 9999999999999})-[:ABOUT]->(e)
        CREATE (g)-[:IN_SCOPE]->(sc)
        CREATE (g)-[:VERIFIED_BY {at: 6000, outcome:'confirmed'}]->(a2)
        CREATE (g)-[:VERIFIED_BY {at: 6100, outcome:'confirmed'}]->(a3)
        CREATE (x1:Step {id:'sy1', agent_id:'a1', at: 7000})-[:READ {via:'use', at: 7000}]->(g)
        CREATE (x2:Step {id:'sy2', agent_id:'a2', at: 7100})-[:READ {via:'use', at: 7100}]->(g)
        CREATE (x3:Step {id:'sy3', agent_id:'a3', at: 7200})-[:READ {via:'use', at: 7200}]->(g)
        """,
    )
    got = Activation(client, graph, Settings(), clock=lambda: NOW).compute(["g2", "f1"])
    g = got["g2"]
    assert g.salience == pytest.approx(1 - math.exp(-(1.5 * 2 + 0.5 * 2)))
    assert g.salience > 0.5
    assert not g.protected and g.protect_reasons == []
    # the boolean rules (here: pinned, an unflagged decision, ...) protect
    assert got["f1"].protected and got["f1"].protect_reasons[0] == "pinned"


def test_pin_caches_salience_and_unpin_removes_the_cache(world):
    client, graph = world
    act = Activation(client, graph, Settings(), clock=lambda: NOW)
    assert act.pin("f2") is True
    assert client.graph(graph).ro_query(
        "MATCH (f:Fact {id:'f2'}) RETURN f.salience, f.salience_at"
    ).result_set == [[0.95, NOW]]
    s = act.strength("f2")
    assert s is not None and s["salience"] >= 0.95 and s["pinned"] and s["salience_inputs"]["pinned"] == 1
    assert act.pin("f2", pinned=False) is True
    assert client.graph(graph).ro_query(
        "MATCH (f:Fact {id:'f2'}) RETURN f.salience, f.pinned"
    ).result_set == [[None, False]]
    assert act.pin("nope") is False


def test_memory_strength_suggests_a_review_date_only_for_salient_facts(world):
    client, graph = world
    act = Activation(client, graph, Settings(), clock=lambda: NOW)
    s1 = act.strength("f1")
    s2 = act.strength("f2")
    assert s1 is not None and s2 is not None
    assert s2["suggested_verify_after"] is None, "not salient: no suggestion"
    sv = s1["suggested_verify_after"]
    assert sv is None or NOW < sv <= NOW + 365 * DAY
    assert s1["fan"] == 2
