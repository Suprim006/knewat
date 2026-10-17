"""P13 (trial 8): quarantine / release / forget respect a fact's other live sources.

Trial 8: rule C1 was required by the compliance memo AND the product spec. "The memo is void: remove the
rules that came only from it" must drop C2/C3 (memo only) and keep C1 (the spec still requires it) and P1
(spec only). Semantics under test (docs/DECISIONS.md D-015):
* quarantine(S) hides a fact only when EVERY Source it derives from is quarantined; the others are listed as
  ``corroborated`` (still visible, with their other sources);
* release_quarantine(S) is the inverse: a quarantined fact with a live Source again is visible again;
* forget_source(S) forgets a fact only when S was its only remaining Source; otherwise it just drops the
  S edge and lists the fact under ``unlinked``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from plexus.embed import HashEmbedder
from plexus.engram import Engram
from plexus.lineage import Lineage
from plexus.relay import Relay

from .conftest import cypher

Rules = SimpleNamespace  # trial 8 in miniature: memo -> C1, C2, C3; spec -> C1, P1; no source -> N1


@pytest.fixture
def rules(client, graph) -> Rules:
    eng, lin, relay = Engram(client, graph, HashEmbedder()), Lineage(client, graph), Relay(client, graph)
    r = Rules()
    r.eng, r.lin, r.relay, r.client, r.graph = eng, lin, relay, client, graph
    r.scope = eng.create_scope("global", "global", now=1)
    r.memo = lin.create_source("urn:compliance-memo", now=1)
    r.spec = lin.create_source("urn:product-spec", now=1)
    r.third = lin.create_source("urn:third", now=1)

    def put(subject, value, **kw):
        return eng.assert_fact(subject, "rule", value, r.scope, "agent", now=100, **kw)["fact_id"]

    r.c1 = put("C1", "audit log required", source_ids=[r.memo, r.spec])
    r.c2 = put("C2", "retention seven years", source_id=r.memo)
    r.c3 = put("C3", "encrypt at rest", source_id=r.memo)
    r.p1 = put("P1", "sso for admins", source_id=r.spec)
    r.n1 = put("N1", "no source at all")
    return r


def status(r: Rules, fact_id: str) -> str:
    return cypher(r.client, r.graph, "MATCH (f:Fact {id: $f}) RETURN f.status", f=fact_id)[0][0]


def statuses(r: Rules) -> dict[str, str]:
    return {k: status(r, getattr(r, k)) for k in ("c1", "c2", "c3", "p1", "n1")}


def linked(r: Rules, fact_id: str) -> list[str]:
    q = "MATCH (:Fact {id: $f})-[:DERIVED_FROM]->(s:Source) RETURN s.id"
    return sorted(x[0] for x in cypher(r.client, r.graph, q, f=fact_id))


# -- quarantine ----------------------------------------------------------------------------------------


def test_quarantine_of_one_source_keeps_a_fact_another_source_supports(rules):
    r = rules.lin.quarantine(rules.memo)
    assert sorted(r["fact_ids"]) == sorted([rules.c2, rules.c3])  # hidden
    assert r["corroborated"] == [{"fact_id": rules.c1, "other_sources": [rules.spec]}]
    assert r["corroborated_total"] == 1
    assert statuses(rules) == {
        "c1": "active",
        "c2": "quarantined",
        "c3": "quarantined",
        "p1": "active",
        "n1": "active",
    }


def test_recall_still_returns_the_corroborated_fact_and_not_the_hidden_ones(rules):
    rules.lin.quarantine(rules.memo)
    ids = {h["fact_id"] for h in rules.eng.recall("rule", rules.scope, k=10)}
    assert rules.c1 in ids and rules.p1 in ids and rules.n1 in ids
    assert rules.c2 not in ids and rules.c3 not in ids


def test_a_fact_is_hidden_once_every_one_of_its_sources_is_quarantined(rules):
    rules.lin.quarantine(rules.memo)
    r = rules.lin.quarantine(rules.spec)
    assert sorted(r["fact_ids"]) == sorted([rules.c1, rules.p1])  # c2 / c3 were hidden by the first call
    assert r["corroborated"] == [] and r["corroborated_total"] == 0
    assert set(statuses(rules).values()) == {"quarantined", "active"}
    assert statuses(rules)["c1"] == "quarantined" and statuses(rules)["n1"] == "active"


def test_the_order_of_the_two_quarantines_does_not_matter(rules):
    rules.lin.quarantine(rules.spec)
    first = rules.lin.quarantine(rules.memo)
    assert sorted(first["fact_ids"]) == sorted([rules.c1, rules.c2, rules.c3])
    assert statuses(rules) == {
        "c1": "quarantined",
        "c2": "quarantined",
        "c3": "quarantined",
        "p1": "quarantined",
        "n1": "active",
    }


def test_quarantine_is_idempotent_and_still_names_the_corroborated_fact(rules):
    rules.lin.quarantine(rules.memo)
    again = rules.lin.quarantine(rules.memo)
    assert again["fact_ids"] == []
    assert [c["fact_id"] for c in again["corroborated"]] == [rules.c1]
    assert status(rules, rules.c1) == "active"


def test_the_blast_radius_describes_only_the_hidden_facts(rules):
    rules.relay.create_tasks([{"id": "t1", "title": "build"}])
    rules.relay.register_agent("agent", "agent", "builder", "test")
    d_only_c1 = rules.relay.record_decision("agent", "t1", "relies on c1", [rules.c1], now=500)
    d_c2 = rules.relay.record_decision("agent", "t1", "relies on c2", [rules.c2], now=501)
    r = rules.lin.quarantine(rules.memo)
    assert r["decision_ids"] == [d_c2] and r["decisions_total"] == 1
    assert d_only_c1 not in r["decision_ids"]


def test_a_superseded_two_source_fact_is_corroborated_too(rules):
    # c1's value changes: the old version (memo + spec) is superseded and keeps both edges
    new = rules.eng.assert_fact(
        "C1", "rule", "audit log and tracing", rules.scope, "agent", source_id=rules.spec, now=200
    )
    assert rules.c1 in new["superseded"]
    r = rules.lin.quarantine(rules.memo)
    assert [c["fact_id"] for c in r["corroborated"]] == [rules.c1]
    assert status(rules, rules.c1) == "superseded"


def test_a_derived_fact_with_its_own_live_source_is_corroborated(rules):
    d = rules.eng.assert_fact(
        "D1", "rule", "derived from c2", rules.scope, "agent", source_id=rules.third, now=300
    )["fact_id"]
    rules.lin.derive_from(d, [rules.c2])  # d -> c2 -> memo, and d -> third
    plain = rules.eng.assert_fact("D2", "rule", "derived from c3", rules.scope, "agent", now=301)["fact_id"]
    rules.lin.derive_from(plain, [rules.c3])  # d2 -> c3 -> memo only
    r = rules.lin.quarantine(rules.memo)
    assert status(rules, d) == "active"  # `third` still supports it
    assert status(rules, plain) == "quarantined"  # the cascade is unchanged for a fact with no other source
    assert d in [c["fact_id"] for c in r["corroborated"]]
    assert plain in r["fact_ids"]


def test_corroborated_list_is_bounded_by_max_detail_but_its_total_is_exact(rules):
    for i in range(4):
        rules.eng.assert_fact(
            f"K{i}",
            "rule",
            f"two sources {i}",
            rules.scope,
            "agent",
            source_ids=[rules.memo, rules.spec],
            now=400,
        )
    r = rules.lin.quarantine(rules.memo, max_detail=2)
    assert r["corroborated_total"] == 5 and len(r["corroborated"]) == 2
    assert r["detail_truncated"] is True


def test_quarantine_marks_the_source(rules):
    q = "MATCH (s:Source {id: $s}) RETURN s.quarantined_at"
    assert cypher(rules.client, rules.graph, q, s=rules.memo) == [[None]]
    rules.lin.quarantine(rules.memo)
    assert cypher(rules.client, rules.graph, q, s=rules.memo)[0][0] is not None
    assert cypher(rules.client, rules.graph, q, s=rules.spec) == [[None]]


# -- release -------------------------------------------------------------------------------------------


def test_release_restores_the_hidden_facts_and_leaves_the_rest(rules):
    rules.lin.quarantine(rules.memo)
    r = rules.lin.release_quarantine(rules.memo)
    assert sorted(r["fact_ids"]) == sorted([rules.c2, rules.c3])
    assert set(statuses(rules).values()) == {"active"}
    assert cypher(
        rules.client, rules.graph, "MATCH (s:Source {id: $s}) RETURN s.quarantined_at", s=rules.memo
    ) == [[None]]


def test_releasing_one_source_brings_back_a_fact_hidden_by_both(rules):
    rules.lin.quarantine(rules.memo)
    rules.lin.quarantine(rules.spec)
    assert status(rules, rules.c1) == "quarantined"
    r = rules.lin.release_quarantine(rules.spec)  # memo is still quarantined, spec is live again
    assert sorted(r["fact_ids"]) == sorted([rules.c1, rules.p1])
    assert statuses(rules) == {
        "c1": "active",
        "c2": "quarantined",
        "c3": "quarantined",
        "p1": "active",
        "n1": "active",
    }


def test_a_released_fact_that_was_corroborated_is_never_changed(rules):
    rules.lin.quarantine(rules.memo)
    before = cypher(rules.client, rules.graph, "MATCH (f:Fact {id: $f}) RETURN properties(f)", f=rules.c1)
    rules.lin.release_quarantine(rules.memo)
    after = cypher(rules.client, rules.graph, "MATCH (f:Fact {id: $f}) RETURN properties(f)", f=rules.c1)
    assert before == after


# -- forget --------------------------------------------------------------------------------------------


def test_forget_of_one_source_unlinks_a_fact_another_source_supports(rules):
    r = rules.lin.forget_source(rules.memo)
    assert sorted(r["fact_ids"]) == sorted([rules.c2, rules.c3])
    assert r["unlinked"] == [{"fact_id": rules.c1, "other_sources": [rules.spec]}]
    assert r["unlinked_total"] == 1
    assert statuses(rules) == {
        "c1": "active",
        "c2": "forgotten",
        "c3": "forgotten",
        "p1": "active",
        "n1": "active",
    }
    assert linked(rules, rules.c1) == [rules.spec]  # the memo edge is gone, the spec edge stays
    ids = {h["fact_id"] for h in rules.eng.recall("rule", rules.scope, k=10)}
    assert rules.c1 in ids and rules.c2 not in ids


def test_forget_is_idempotent(rules):
    rules.lin.forget_source(rules.memo)
    again = rules.lin.forget_source(rules.memo)
    assert again["fact_ids"] == [] and again["unlinked"] == [] and again["unlinked_total"] == 0
    assert status(rules, rules.c1) == "active"


def test_forgetting_the_last_source_forgets_the_fact(rules):
    rules.lin.forget_source(rules.memo)
    r = rules.lin.forget_source(rules.spec)
    assert sorted(r["fact_ids"]) == sorted([rules.c1, rules.p1])
    assert r["unlinked"] == []
    assert status(rules, rules.c1) == "forgotten"


def test_forget_flags_only_decisions_built_on_forgotten_facts(rules):
    rules.relay.create_tasks([{"id": "t1", "title": "build"}])
    rules.relay.register_agent("agent", "agent", "builder", "test")
    d1 = rules.relay.record_decision("agent", "t1", "relies on c1", [rules.c1], now=500)
    d2 = rules.relay.record_decision("agent", "t1", "relies on c2", [rules.c2], now=501)
    r = rules.lin.forget_source(rules.memo)
    assert r["decision_ids"] == [d2]
    flagged = cypher(rules.client, rules.graph, "MATCH (d:Decision) WHERE d.flagged = true RETURN d.id")
    assert flagged == [[d2]] and d1 not in r["decision_ids"]


def test_forget_with_a_quarantined_remaining_source_hides_the_fact(rules):
    rules.lin.quarantine(rules.spec)  # c1 is still visible: the memo supports it
    assert status(rules, rules.c1) == "active"
    r = rules.lin.forget_source(rules.memo)
    assert [u["fact_id"] for u in r["unlinked"]] == [rules.c1]
    assert status(rules, rules.c1) == "quarantined"  # what is left is a quarantined source only
    assert rules.lin.release_quarantine(rules.spec)["fact_ids"].count(rules.c1) == 1
    assert status(rules, rules.c1) == "active"


def test_forget_of_a_hidden_two_source_fact_drops_only_that_edge(rules):
    rules.lin.quarantine(rules.memo)
    rules.lin.quarantine(rules.spec)
    r = rules.lin.forget_source(rules.memo)
    assert status(rules, rules.c1) == "quarantined" and linked(rules, rules.c1) == [rules.spec]
    assert sorted(r["fact_ids"]) == sorted(
        [rules.c2, rules.c3]
    )  # quarantined facts of the memo are forgotten for good
    assert [u["fact_id"] for u in r["unlinked"]] == [rules.c1]


def test_forget_mode_quarantine_dispatches_to_the_new_quarantine(rules):
    r = rules.lin.forget_source(rules.memo, mode="quarantine")
    assert [c["fact_id"] for c in r["corroborated"]] == [rules.c1]


# -- why and the readers of fact -> source edges -------------------------------------------------------


def test_why_lists_every_source_of_the_fact(rules):
    w = rules.lin.why(rules.c1)
    fact = next(f for f in w["facts"] if f["id"] == rules.c1)
    assert sorted(fact["sources"]) == sorted([rules.memo, rules.spec])
    assert sorted(w["sources"]) == sorted([rules.memo, rules.spec])
    derived = sorted(e["to"] for e in w["edges"] if e["rel"] == "DERIVED_FROM" and e["from"] == rules.c1)
    assert derived == sorted([rules.memo, rules.spec])


def test_why_shows_the_sources_that_are_left_after_a_forget(rules):
    rules.lin.forget_source(rules.memo)
    fact = next(f for f in rules.lin.why(rules.c1)["facts"] if f["id"] == rules.c1)
    assert fact["sources"] == [rules.spec]
