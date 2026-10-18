"""Slice 5a: pin / strength / sweep / restore on the activation service.

A sweep only moves facts to 'dormant' and a restore brings back exactly the previous graph.
Nothing is ever deleted by decay."""

from __future__ import annotations

import pytest

from knewat.activation import Activation, Settings
from knewat.activation.model import DAY_MS, neutral_activation

from .conftest import cypher, write

NOW = 5_000 * DAY_MS


@pytest.fixture
def act(client, graph) -> Activation:
    return Activation(client, graph, Settings(), clock=lambda: NOW)


class World:
    """A scope with one fact of every kind a sweep has to tell apart. All are 400 days old (A ~ -8.7)."""

    def __init__(self, eng, relay, lin, scope, client, graph):
        self.eng, self.scope, self.client, self.graph = eng, scope, client, graph
        old = NOW - 400 * DAY_MS
        relay.register_agent("alice", "alice", "x", "t")
        relay.register_agent("bob", "bob", "x", "t")
        relay.create_tasks([{"id": "t1", "title": "ship"}])
        self.faint = self.add("faint", "unused and old", old)
        self.faint2 = self.add("faint2", "also unused", old)
        self.fresh = self.add("fresh", "created yesterday", NOW - DAY_MS)
        self.used = self.add("used", "used an hour ago", old)
        st = lin.record_step("bob", 1, at=NOW - 3_600_000)
        lin.link_step(st, read_ids=[self.used])
        self.pinned = self.add("pinned", "pinned by a human", old)
        write(client, graph, "MATCH (f:Fact {id:$f}) SET f.pinned = true", f=self.pinned)
        self.decided = self.add("decided", "a decision rests on it", old)
        relay.record_decision("alice", "t1", "rely", [self.decided], now=old)
        self.carried = self.add("carried", "a handoff carries it", old)
        relay.handoff("alice", "bob", "t1", "note", [], [self.carried], now=old)
        self.suspect = self.add("suspect", "its code changed", old)
        write(
            client,
            graph,
            "MATCH (f:Fact {id:$f}) SET f.verify_state = 'suspect', f.suspect_since = $t",
            f=self.suspect,
            t=NOW - DAY_MS,
        )
        self.review = self.add("review", "review date passed", old)
        write(client, graph, "MATCH (f:Fact {id:$f}) SET f.verify_after = $t", f=self.review, t=NOW - DAY_MS)
        self.old_v = self.add("version", "v1", old)
        self.new_v = eng.assert_fact("Thing version", "note", "v2", scope, "alice", now=old + DAY_MS)[
            "fact_id"
        ]
        write(client, graph, "MATCH (f:Fact) SET f.surprise = 0.0")

    def add(self, name: str, value: str, at: int) -> str:
        return self.eng.assert_fact(f"Thing {name}", "note", value, self.scope, "alice", now=at)["fact_id"]

    @property
    def shielded(self):
        """Facts a sweep must never move: protected, suspect or past their review date."""
        return {
            self.pinned,
            self.decided,
            self.carried,
            self.suspect,
            self.review,
            self.new_v,  # supersedes the old one
        }


@pytest.fixture
def w(eng, relay, lin, scope, client, graph) -> World:
    return World(eng, relay, lin, scope, client, graph)


def status(client, graph, fid):
    return cypher(client, graph, "MATCH (f:Fact {id:$f}) RETURN f.status", f=fid)[0][0]


def dump(client, graph):
    """Every node and edge with all properties (embeddings included), in a comparable form."""
    g = client.graph(graph)
    nodes = sorted(
        (sorted(n.labels), sorted((k, repr(v)) for k, v in n.properties.items()))
        for (n,) in g.ro_query("MATCH (n) RETURN n").result_set
    )
    edges = sorted(
        (
            e.src_node,
            e.dest_node,
            e.relation,
            sorted((k, repr(v)) for k, v in e.properties.items()),
        )
        for (e,) in g.ro_query("MATCH ()-[e]->() RETURN e").result_set
    )
    return nodes, edges


# ---------------------------------------------------------------- pin
def test_pin_and_unpin_set_the_flag_and_protect(act, w):
    assert act.pin(w.faint) is True
    fa = act.compute([w.faint], NOW)[w.faint]
    assert fa.pinned and fa.protect_reasons == ["pinned"]
    assert act.pin(w.faint, False) is True
    assert not act.compute([w.faint], NOW)[w.faint].pinned
    assert act.pin("no-such-fact") is False


# ---------------------------------------------------------------- strength
def test_strength_reports_the_computation_and_a_one_line_explanation(act, w):
    s = act.strength(w.used)
    assert s["fact_id"] == w.used and s["status"] == "active" and s["protected"] is False
    assert s["a0"] == pytest.approx(neutral_activation())
    assert s["activation"] > s["a0"] - 1  # an hour-old use dominates
    assert 0.9 <= s["multiplier"] <= 1.0 and s["floor"] == 0.9  # the default floor
    assert (s["counts"]["use"], s["counts"]["recall"]) == (1, 0)
    assert s["last_use"] == NOW - 3_600_000
    assert "used 1x" in s["explanation"] and "last use 1 hour ago" in s["explanation"]
    assert act.strength("nope") is None


def test_strength_explains_protection_and_age(act, w):
    s = act.strength(w.decided)
    assert s["protected"] and s["protect_reasons"] == [s["protect_reasons"][0]]
    assert s["protect_reasons"][0].startswith("decision:")
    assert "protected: decision" in s["explanation"]
    assert s["multiplier"] >= 0.75 - 1e-9
    assert "never used" in act.strength(w.faint)["explanation"]


def test_strength_never_changes_anything(act, w, client, graph):
    before = dump(client, graph)
    act.strength(w.faint)
    act.compute([w.faint], NOW)
    assert dump(client, graph) == before


# ---------------------------------------------------------------- sweep
def test_dry_run_lists_only_unprotected_unsuspected_faint_facts_and_writes_nothing(act, w, client, graph):
    before = dump(client, graph)
    r = act.sweep(w.scope)
    assert r["dry_run"] is True
    assert {c["fact_id"] for c in r["candidates"]} == {w.faint, w.faint2}
    assert r["would_move"] == len(r["candidates"]) and r["moved"] == []
    assert r["threshold"] == pytest.approx(neutral_activation() - 2)
    assert dump(client, graph) == before


def test_protected_suspect_used_and_fresh_facts_are_never_candidates(act, w):
    ids = {c["fact_id"] for c in act.sweep(w.scope, threshold=100.0)["candidates"]}
    assert ids.isdisjoint(w.shielded)
    assert {w.faint, w.faint2} <= ids


def test_a_lower_threshold_selects_fewer(act, w):
    assert act.sweep(w.scope, threshold=-50.0)["candidates"] == []


def test_limit_caps_the_candidates_and_reports_the_rest(act, w):
    r = act.sweep(w.scope, threshold=100.0, limit=1)
    assert len(r["candidates"]) == 1 and r["truncated"] is True and r["would_move"] == 1


def test_apply_moves_to_dormant_keeps_prior_status_and_deletes_nothing(act, w, client, graph):
    n_nodes = cypher(client, graph, "MATCH (n) RETURN count(n)")[0][0]
    n_edges = cypher(client, graph, "MATCH ()-[r]->() RETURN count(r)")[0][0]
    r = act.sweep(w.scope, dry_run=False)
    assert set(r["moved"]) == {w.faint, w.faint2} and r["dry_run"] is False
    for fid in (w.faint, w.faint2):
        assert cypher(
            client, graph, "MATCH (f:Fact {id:$f}) RETURN f.status, f.prior_status, f.dormant_at", f=fid
        ) == [["dormant", "active", NOW]]
    assert status(client, graph, w.used) == "active" and status(client, graph, w.decided) == "active"
    assert cypher(client, graph, "MATCH (n) RETURN count(n)")[0][0] == n_nodes
    assert cypher(client, graph, "MATCH ()-[r]->() RETURN count(r)")[0][0] == n_edges
    again = act.sweep(w.scope, dry_run=False)
    assert again["moved"] == [] and again["candidates"] == [], (
        "a dormant fact is not active, so not swept twice"
    )


def test_apply_rechecks_protection_inside_the_statement(act, w, client, graph, relay):
    stale = act.sweep(w.scope, threshold=100.0)["candidates"]  # a stale listing: faint ones
    assert w.faint in {c["fact_id"] for c in stale}
    act.pin(w.faint)  # protected between the listing and the write
    moved = act.apply_sweep([c["fact_id"] for c in stale], NOW)
    assert w.faint not in moved and status(client, graph, w.faint) == "active"
    assert w.faint2 in moved


def test_apply_never_touches_protected_facts_even_if_asked_directly(act, w, client, graph):
    moved = act.apply_sweep(list(w.shielded), NOW)
    assert moved == []
    assert all(status(client, graph, f) in ("active", "superseded") for f in w.shielded)


def test_apply_ignores_facts_that_are_not_active(act, w, client, graph):
    assert act.apply_sweep([w.old_v, "ghost"], NOW) == [], "a superseded fact is history, not a candidate"
    assert status(client, graph, w.old_v) == "superseded"


# ---------------------------------------------------------------- restore
def test_sweep_then_restore_gives_an_identical_graph(act, w, client, graph):
    before = dump(client, graph)
    moved = act.sweep(w.scope, dry_run=False)["moved"]
    assert moved and dump(client, graph) != before
    for fid in moved:
        r = act.restore(fid)
        assert r == {"fact_id": fid, "restored": True, "status": "active", "was": "dormant"}
    assert dump(client, graph) == before


def test_restore_of_a_live_or_unknown_fact_is_reported_not_applied(act, w, client, graph):
    before = dump(client, graph)
    assert act.restore(w.used) == {"fact_id": w.used, "restored": False, "status": "active", "was": "active"}
    assert act.restore("ghost") is None
    assert dump(client, graph) == before


def test_a_restored_fact_is_recalled_again_and_dormant_is_hidden_meanwhile(act, w, eng, scope):
    act.sweep(w.scope, dry_run=False)
    assert "Thing faint note: unused and old" not in [
        h["text"] for h in eng.recall("faint unused old", scope, k=20)
    ]
    act.restore(w.faint)
    assert "Thing faint note: unused and old" in [
        h["text"] for h in eng.recall("faint unused old", scope, k=20)
    ]


# ------------------------------------------------ the in-statement protection re-check, rule by rule
def _old(eng, scope, name, value, agent="alice", at=NOW - 400 * DAY_MS):
    return eng.assert_fact(f"Thing {name}", "note", value, scope, agent, now=at)["fact_id"]


def test_apply_skips_each_kind_of_protected_fact_and_moves_a_plain_one(act, eng, lin, scope, client, graph):
    plain = _old(eng, scope, "plain", "nothing protects it")
    a = _old(eng, scope, "clash", "alice says 80")
    b = eng.assert_fact("Thing clash", "note", "bob says 8080", scope, "bob", now=NOW - 399 * DAY_MS)[
        "fact_id"
    ]
    src = lin.create_source("https://docs.example/x", kind="doc", trust=1.0, now=1)
    trusted = eng.assert_fact(
        "Thing doc", "note", "from a trusted doc", scope, "alice", source_id=src, now=NOW - 400 * DAY_MS
    )
    write(client, graph, "MATCH (s:Source {id:$s}) SET s.trust = 'high'", s=src)
    cases = {"contradicted-old": a, "contradicting-new": b, "trusted": trusted["fact_id"]}
    for name, fid in cases.items():
        assert act.apply_sweep([fid], NOW) == [], name
    assert act.apply_sweep([plain], NOW) == [plain]
    for fid in cases.values():
        assert status(client, graph, fid) == "active"


def test_a_flagged_decision_no_longer_protects(act, eng, relay, scope, client, graph):
    f = _old(eng, scope, "decided", "a decision used to rest on it")
    relay.register_agent("alice", "alice", "x", "t")
    relay.create_tasks([{"id": "t1", "title": "ship"}])
    d = relay.record_decision("alice", "t1", "rely", [f], now=NOW - 400 * DAY_MS)
    assert act.apply_sweep([f], NOW) == []
    write(client, graph, "MATCH (d:Decision {id:$d}) SET d.flagged = true", d=d)
    assert [c["fact_id"] for c in act.sweep(scope, 100.0)["candidates"]] == [f]
    assert act.apply_sweep([f], NOW) == [f]


def test_apply_is_bounded_by_the_ids_it_is_given(act, w, client, graph):
    before = cypher(client, graph, "MATCH (f:Fact {status:'dormant'}) RETURN count(f)")[0][0]
    act.apply_sweep([w.faint], NOW)
    assert cypher(client, graph, "MATCH (f:Fact {status:'dormant'}) RETURN count(f)")[0][0] == before + 1


def test_limits_are_validated(act, w):
    with pytest.raises(ValueError, match="limit"):
        act.sweep(w.scope, limit=0)
    with pytest.raises(ValueError, match="limit"):
        act.sweep(w.scope, limit=201)
    with pytest.raises(ValueError, match="scan"):
        act.sweep(w.scope, scan=0)
