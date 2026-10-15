"""FIX-P7 P7-02: ``assert_fact`` treats a ``dormant`` fact as a current fact; ``restore`` never revives a fact
whose successor already exists."""

from __future__ import annotations

from .conftest import cypher, row, sweep_to_dormant


# -- P7-02 ----------------------------------------------------------------------------------------------
def test_assert_supersedes_a_dormant_fact(eng, mem, act, client, graph, clock):
    f = mem.fact("timeout", "30 seconds")
    sweep_to_dormant(act, f)
    clock.t = 3_000_000
    r = eng.assert_fact("Payments", "timeout", "60 seconds", mem.proj, "alice", now=clock.t, supersede=True)
    assert r["superseded"] == [f] and r["contradicts"] == [] and r["duplicate_of"] is None
    status, valid_to, _, _ = row(client, graph, f)
    assert (status, valid_to) == ("superseded", 3_000_000)
    edge = cypher(
        client,
        graph,
        "MATCH (n:Fact {id:$n})-[:SUPERSEDES]->(o:Fact {id:$o}) RETURN count(*)",
        n=r["fact_id"],
        o=f,
    )
    assert edge == [[1]]
    # restore finds nothing to revive: the fact is history now
    out = act.restore(f)
    assert out["restored"] is False and out["status"] == "superseded"
    n_active = cypher(
        client,
        graph,
        "MATCH (f:Fact {predicate:'timeout', status:'active'}) RETURN count(f)",
    )[0][0]
    assert n_active == 1


def test_another_agents_new_value_contradicts_a_dormant_fact_and_restore_still_works(
    eng, mem, act, relay, client, graph, clock
):
    relay.register_agent("bob", "bob", "builder", "test")
    f = mem.fact("timeout", "30 seconds")
    sweep_to_dormant(act, f)
    clock.t = 3_000_000
    r = eng.assert_fact("Payments", "timeout", "60 seconds", mem.proj, "bob", now=clock.t, supersede=False)
    assert r["contradicts"] == [f] and r["superseded"] == []
    # a recorded disagreement is a legitimate state: restore brings the old belief back, linked by CONTRADICTS
    assert act.restore(f)["restored"] is True


def test_asserting_the_same_value_wakes_a_dormant_fact(eng, mem, act, client, graph, clock):
    f = mem.fact("timeout", "30 seconds")
    sweep_to_dormant(act, f)
    clock.t = 3_000_000
    r = eng.assert_fact("Payments", "timeout", "30 seconds", mem.proj, "alice", now=clock.t, supersede=True)
    assert r["duplicate_of"] == f and r["fact_id"] == f
    assert row(client, graph, f)[0] == "active"
    pr = cypher(client, graph, "MATCH (f:Fact {id:$f}) RETURN f.prior_status, f.dormant_at", f=f)
    assert pr == [[None, None]]


def test_restore_refuses_when_a_newer_active_fact_exists(eng, mem, act, client, graph, clock):
    """Data from before the fix: a dormant fact and a newer active one (same entity, predicate, scope)."""
    old = mem.fact("timeout", "30 seconds")
    clock.t = 2_000_000
    new = mem.fact("timeout", "60 seconds")  # supersede=True closes `old`
    client.graph(graph).query(
        "MATCH (f:Fact {id:$f}) SET f.status = 'dormant', f.prior_status = 'active', f.dormant_at = 5, "
        "f.valid_to = 9999999999999",
        {"f": old},
    )
    out = act.restore(old)
    assert out["restored"] is False and out["status"] == "dormant"
    assert out["reason"] == "already_superseded" and out["superseded_by"] == [new]
    assert row(client, graph, old)[0] == "dormant"
