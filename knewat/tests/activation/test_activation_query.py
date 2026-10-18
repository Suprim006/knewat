"""Slice 3b: ``activation/activation`` gathers the events and protection reasons; Python turns them into A."""

from __future__ import annotations

import math

import pytest

from knewat.activation import Activation, Settings
from knewat.activation.model import DAY_MS

from .conftest import write

NOW = 5_000 * DAY_MS


@pytest.fixture
def act(client, graph) -> Activation:
    return Activation(client, graph, Settings())


@pytest.fixture
def fact(eng, scope):
    """One fact created 10 days before NOW by alice."""
    return eng.assert_fact("API", "database", "PostgreSQL 16", scope, "alice", now=NOW - 10 * DAY_MS)[
        "fact_id"
    ]


def kinds(fa):
    return sorted((e.kind, e.t) for e in fa.events)


def test_a_fresh_fact_has_only_its_creation_event(act, fact):
    fa = act.compute([fact], NOW)[fact]
    assert kinds(fa) == [("create", NOW - 10 * DAY_MS)]
    # surprise of the first fact is 0.5 -> 1 + round(2) = 3 pseudo events at creation
    expected = math.log(4 * (10 * 86400) ** -0.5)
    assert fa.activation == pytest.approx(expected)
    assert not fa.protected and fa.status == "active" and fa.verify_state == "verified"


def test_unknown_ids_give_no_entry(act, fact):
    assert set(act.compute([fact, "ghost"], NOW)) == {fact}
    assert act.compute([], NOW) == {}


def test_read_edges_count_by_via_and_absent_via_is_recall(act, eng, lin, scope, fact, client, graph):
    s1 = lin.record_step("bob", 1, at=NOW - 2 * DAY_MS)
    lin.record_recall("bob", s1, "database", scope, 3, [{"fact_id": fact}], now=NOW - 2 * DAY_MS)
    s2 = lin.record_step("bob", 2, at=NOW - DAY_MS)
    lin.link_step(s2, read_ids=[fact])
    s3 = lin.record_step("carol", 1, at=NOW - 3 * DAY_MS)
    write(client, graph, "MATCH (s:Step {id:$s}), (f:Fact {id:$f}) CREATE (s)-[:READ]->(f)", s=s3, f=fact)
    fa = act.compute([fact], NOW)[fact]
    got = sorted((e.kind, e.t, e.w) for e in fa.events)
    assert ("use", NOW - DAY_MS, 1.0) in got
    assert ("recall", NOW - 2 * DAY_MS, 0.3) in got
    assert ("recall", NOW - 3 * DAY_MS, 0.3) in got, "a READ without via/at: recall at the Step's time"


def test_decision_handoff_reassert_and_verification_events(act, eng, relay, scope, fact, client, graph):
    relay.register_agent("alice", "alice", "x", "t")
    relay.register_agent("bob", "bob", "x", "t")
    relay.create_tasks([{"id": "t1", "title": "ship"}])
    relay.record_decision("alice", "t1", "use pg", [fact], now=NOW - 5 * DAY_MS)
    relay.handoff("alice", "bob", "t1", "note", [], [fact], now=NOW - 4 * DAY_MS)
    dup = eng.assert_fact("API", "database", "PostgreSQL 16", scope, "bob", now=NOW - 3 * DAY_MS)
    assert dup["duplicate_of"] == fact
    write(
        client,
        graph,
        "MATCH (f:Fact {id:$f}), (a:Agent {id:'bob'}) "
        "CREATE (f)-[:VERIFIED_BY {at:$at, commit:'c', outcome:'confirmed'}]->(a)",
        f=fact,
        at=NOW - 2 * DAY_MS,
    )
    fa = act.compute([fact], NOW)[fact]
    got = {(e.kind, e.t): e.w for e in fa.events}
    assert got[("decision", NOW - 5 * DAY_MS)] == 1.0
    assert got[("handoff", NOW - 4 * DAY_MS)] == 1.0
    assert got[("reassert", NOW - 3 * DAY_MS)] == 1.0
    assert got[("verified", NOW - 2 * DAY_MS)] == 2.0
    assert all(k != "reassert" or t > NOW - 10 * DAY_MS for k, t in got), (
        "the creating ASSERTED_BY is no re-assert"
    )


def test_events_after_now_are_ignored(act, lin, fact):
    s = lin.record_step("bob", 1, at=NOW + DAY_MS)
    lin.link_step(s, read_ids=[fact])
    assert [e.kind for e in act.compute([fact], NOW)[fact].events] == ["create"]
    assert "use" in [e.kind for e in act.compute([fact], NOW + 2 * DAY_MS)[fact].events]


def test_only_the_newest_k_read_events_are_kept(eng, lin, scope, fact, client, graph):
    for i in range(1, 61):
        s = lin.record_step("bob", i, at=NOW - 100 * DAY_MS + i * DAY_MS)
        lin.link_step(s, read_ids=[fact])
    a = Activation(client, graph, Settings(events=50))
    reads = [e for e in a.compute([fact], NOW)[fact].events if e.kind == "use"]
    assert len(reads) <= 50
    assert min(e.t for e in reads) == NOW - 100 * DAY_MS + 12 * DAY_MS, (
        "K counts all events: 49 reads + the creation"
    )


def test_surprise_and_pin_are_read_from_the_fact(act, eng, scope, client, graph):
    f = eng.assert_fact("API", "cache", "Redis", scope, "alice", now=NOW - DAY_MS)["fact_id"]
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.surprise = 0.9", f=f)
    fa = act.compute([f], NOW)[f]
    assert fa.surprise == pytest.approx(0.9) and not fa.pinned
    write(client, graph, "MATCH (f:Fact {id:$f}) SET f.pinned = true", f=f)
    fb = act.compute([f], NOW)[f]
    assert fb.pinned and fb.protected and fb.protect_reasons == ["pinned"]


def test_facts_written_before_p7_have_neutral_defaults(act, fact, client, graph):
    write(client, graph, "MATCH (f:Fact {id:$f}) REMOVE f.surprise", f=fact)
    fa = act.compute([fact], NOW)[fact]
    assert fa.surprise == 0.0 and fa.verify_state == "verified" and fa.suspect_since == 0
    assert fa.activation == pytest.approx(math.log((10 * 86400) ** -0.5))


# ---------------------------------------------------------------- protection
def test_an_unflagged_decision_protects_and_a_flagged_one_does_not(act, relay, fact, client, graph):
    relay.register_agent("alice", "alice", "x", "t")
    relay.create_tasks([{"id": "t1", "title": "ship"}])
    d = relay.record_decision("alice", "t1", "use pg", [fact], now=NOW - DAY_MS)
    fa = act.compute([fact], NOW)[fact]
    assert fa.protected and fa.protect_reasons == [f"decision:{d}"]
    write(client, graph, "MATCH (d:Decision {id:$d}) SET d.flagged = true", d=d)
    assert not act.compute([fact], NOW)[fact].protected


def test_a_carrying_handoff_protects(act, relay, fact):
    relay.register_agent("alice", "alice", "x", "t")
    relay.register_agent("bob", "bob", "x", "t")
    relay.create_tasks([{"id": "t1", "title": "ship"}])
    h = relay.handoff("alice", "bob", "t1", "note", [], [fact], now=NOW - DAY_MS)
    assert act.compute([fact], NOW)[fact].protect_reasons == [f"handoff:{h}"]


def test_supersedes_protects_the_newer_fact_only_and_contradicts_both_ends(act, eng, scope):
    old = eng.assert_fact("API", "version", "v1", scope, "alice", now=NOW - 20 * DAY_MS)["fact_id"]
    new = eng.assert_fact("API", "version", "v2", scope, "alice", now=NOW - 10 * DAY_MS)["fact_id"]
    got = act.compute([old, new], NOW)
    assert got[new].protect_reasons == [f"supersedes:{old}"]
    assert not got[old].protected, "the closed fact is only the target of SUPERSEDES"
    x = eng.assert_fact("API", "port", "80", scope, "alice", now=NOW - 9 * DAY_MS)["fact_id"]
    y = eng.assert_fact("API", "port", "8080", scope, "bob", now=NOW - 8 * DAY_MS)["fact_id"]
    got = act.compute([x, y], NOW)
    assert got[x].protect_reasons == [f"contradicts:{y}"] and got[y].protect_reasons == [f"contradicts:{x}"]


def test_a_high_trust_source_protects_but_a_float_trust_is_harmless(act, lin, eng, scope, client, graph):
    src = lin.create_source("https://docs.example/pg", kind="doc", trust=1.0, now=1)
    f = eng.assert_fact("API", "db", "pg", scope, "alice", source_id=src, now=NOW - 30 * DAY_MS)["fact_id"]
    assert not act.compute([f], NOW)[f].protected, "today's Source.trust is a float, never 'high'"
    write(client, graph, "MATCH (s:Source {id:$s}) SET s.trust = 'high'", s=src)
    assert act.compute([f], NOW)[f].protect_reasons == [f"trusted_source:{src}"]


def test_a_fact_derived_two_hops_from_a_high_trust_source_is_protected(act, lin, eng, scope, client, graph):
    src = lin.create_source("https://docs.example/pg", kind="doc", trust=1.0, now=1)
    write(client, graph, "MATCH (s:Source {id:$s}) SET s.trust = 'high'", s=src)
    base = eng.assert_fact("API", "db", "pg", scope, "alice", source_id=src, now=NOW - 30 * DAY_MS)["fact_id"]
    derived = eng.assert_fact("API", "cache", "redis", scope, "alice", now=NOW - 30 * DAY_MS)["fact_id"]
    lin.derive_from(derived, [base])
    assert act.compute([derived], NOW)[derived].protect_reasons == [f"trusted_source:{src}"]


# ------------------------------------------------ suspect facts are not strengthened by recall
def test_recall_events_after_suspect_since_are_ignored_for_a_suspect_fact(
    act, eng, lin, scope, fact, client, graph
):
    s1 = lin.record_step("bob", 1, at=NOW - 6 * DAY_MS)
    lin.record_recall("bob", s1, "q", scope, 3, [{"fact_id": fact}], now=NOW - 6 * DAY_MS)
    s2 = lin.record_step("bob", 2, at=NOW - 2 * DAY_MS)
    lin.record_recall("bob", s2, "q", scope, 3, [{"fact_id": fact}], now=NOW - 2 * DAY_MS)
    s3 = lin.record_step("bob", 3, at=NOW - DAY_MS)
    lin.link_step(s3, read_ids=[fact])
    before = act.compute([fact], NOW)[fact]
    assert [e.t for e in before.events if e.kind == "recall"] == [NOW - 2 * DAY_MS, NOW - 6 * DAY_MS]
    write(
        client,
        graph,
        "MATCH (f:Fact {id:$f}) SET f.verify_state = 'suspect', f.suspect_since = $t",
        f=fact,
        t=NOW - 4 * DAY_MS,
    )
    after = act.compute([fact], NOW)[fact]
    assert after.verify_state == "suspect"
    assert [e.t for e in after.events if e.kind == "recall"] == [NOW - 6 * DAY_MS]
    assert any(e.kind == "use" for e in after.events), "a use is not a recall"
    assert after.activation < before.activation
