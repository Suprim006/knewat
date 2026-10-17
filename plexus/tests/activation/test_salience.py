"""D-013 P2: graded salience from the graph (every input fires once), protection by salience, the pin cache,
and the add-mode activation / sweep margin through the service."""

from __future__ import annotations

import math

import pytest

from plexus.activation import Activation, Settings
from plexus.activation.service import SALIENCE_W, salience_of

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


def test_salience_alone_protects_and_the_add_mode_activation_uses_it(world):
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
    act_mult = Activation(client, graph, Settings(), clock=lambda: NOW)
    act_add = Activation(client, graph, Settings(act_mode="add"), clock=lambda: NOW)
    fa = act_mult.compute(["g1"])["g1"]
    assert fa.salience == pytest.approx(1 - math.exp(-2.0))  # 1.5 verified + 0.5 (2 agents - 1)
    assert fa.protected and fa.protect_reasons == [f"salience:{fa.salience:.2f}"]
    assert fa.decays == [], "mult mode: the D-012 model, no per-event decay"
    fb = act_add.compute(["g1"])["g1"]
    assert fb.decays and len(fb.decays) == len(fb.events)
    assert fb.decays[0] == pytest.approx(0.177 * (1 - 0.4 * fb.salience)), "salience slows the decay"
    assert fb.activation != fa.activation
    # the sweep threshold follows the mode: A0 - 2 under D-012, A0 - 0.72 under Pavlik-Anderson
    assert act_mult.sweep("global", now=NOW)["threshold"] == pytest.approx(act_mult.settings.neutral - 2.0)
    assert act_add.sweep("global", now=NOW)["threshold"] == pytest.approx(act_add.settings.neutral - 0.72)


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
    act = Activation(client, graph, Settings(act_mode="add"), clock=lambda: NOW)
    s1 = act.strength("f1")
    s2 = act.strength("f2")
    assert s1 is not None and s2 is not None
    assert s2["suggested_verify_after"] is None, "not salient: no suggestion"
    sv = s1["suggested_verify_after"]
    assert sv is None or NOW < sv <= NOW + 365 * DAY
    assert s1["mode"] == "add" and -0.05 <= s1["act_term"] <= 0.05 and s1["fan"] == 2
