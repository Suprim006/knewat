"""P13 (trial 8): a fact several documents support links to ALL of them; a duplicate assert corroborates.

Trial 8: rule C1 was required by the compliance memo AND the product spec, but ``assert_fact`` took one
``source_id``, so every run linked C1 to the memo only; re-asserting C1 from the spec was a no-op
(``duplicate_of``) that dropped the spec. ``source_ids`` links every listed Source in the one assert statement
and the duplicate path links the sources it did not have yet (``sources_added``).
"""

from __future__ import annotations

import pytest

from knewat.embed import FastEmbedder, HashEmbedder
from knewat.engram import Engram
from knewat.engram.errors import UnknownReference
from knewat.lineage import Lineage


def q(client, graph, cypher, **p):
    return client.graph(graph).ro_query(cypher, p or None).result_set


def sources_of(client, graph, fact_id):
    return sorted(
        r[0]
        for r in q(client, graph, "MATCH (:Fact {id: $f})-[:DERIVED_FROM]->(s:Source) RETURN s.id", f=fact_id)
    )


@pytest.fixture
def svc(client, graph):
    eng, lin = Engram(client, graph, HashEmbedder()), Lineage(client, graph)
    scope = eng.create_scope("global", "global", now=1)
    memo = lin.create_source("urn:memo", now=1)
    spec = lin.create_source("urn:spec", now=1)
    third = lin.create_source("urn:third", now=1)
    return eng, lin, scope, memo, spec, third


def test_source_ids_links_every_listed_source(client, graph, svc):
    eng, _, scope, memo, spec, _ = svc
    r = eng.assert_fact("Rule C1", "requires", "audit log", scope, "a", source_ids=[memo, spec], now=100)
    assert sources_of(client, graph, r["fact_id"]) == sorted([memo, spec])
    assert "sources_added" not in r  # a new fact: nothing to add to; the response stays small


def test_source_id_and_source_ids_are_unioned_without_a_double_edge(client, graph, svc):
    eng, _, scope, memo, spec, third = svc
    r = eng.assert_fact(
        "Rule C1", "requires", "audit log", scope, "a", source_id=memo, source_ids=[memo, spec, spec], now=100
    )
    assert sources_of(client, graph, r["fact_id"]) == sorted([memo, spec])
    n = q(
        client,
        graph,
        "MATCH (:Fact {id: $f})-[d:DERIVED_FROM]->(:Source {id: $s}) RETURN count(d)",
        f=r["fact_id"],
        s=memo,
    )
    assert n == [[1]]


def test_an_unknown_source_id_rejects_the_whole_call_and_writes_nothing(client, graph, svc):
    eng, _, scope, memo, _, _ = svc
    before = q(client, graph, "MATCH (n) RETURN count(n)")
    with pytest.raises(UnknownReference) as exc:
        eng.assert_fact("Brand new", "p", "v", scope, "a", source_ids=[memo, "nope"], now=5)
    assert exc.value.kind == "source" and exc.value.ids == ["nope"]
    assert q(client, graph, "MATCH (n) RETURN count(n)") == before  # not even the Entity
    eng.assert_fact("S", "p", "one", scope, "a", now=6)  # an existing entity: same, nothing appears
    before = q(client, graph, "MATCH (n) RETURN count(n)")
    with pytest.raises(UnknownReference):
        eng.assert_fact("S", "p", "two", scope, "z", source_ids=["nope"], now=7)
    assert q(client, graph, "MATCH (n) RETURN count(n)") == before


def test_source_ids_accept_sources_only(client, graph, svc):
    eng, _, scope, memo, _, _ = svc
    first = eng.assert_fact("S", "p", "one", scope, "a", now=6)
    with pytest.raises(UnknownReference) as exc:  # a Fact id is a valid derived_from origin, not a source
        eng.assert_fact("S", "q", "two", scope, "a", source_ids=[first["fact_id"]], now=7)
    assert exc.value.kind == "source" and exc.value.ids == [first["fact_id"]]


def test_at_most_twenty_source_ids(client, graph, svc):
    eng, _, scope, memo, _, _ = svc
    with pytest.raises(ValueError, match="20"):
        eng.assert_fact("S", "p", "v", scope, "a", source_ids=[f"x{i}" for i in range(21)], now=1)
    assert q(client, graph, "MATCH (e:Entity) RETURN count(e)") == [[0]]


def test_a_duplicate_assert_from_a_new_source_corroborates(client, graph, svc):
    eng, _, scope, memo, spec, _ = svc
    first = eng.assert_fact("Rule C1", "requires", "audit log", scope, "a", source_id=memo, now=100)
    again = eng.assert_fact("Rule C1", "requires", "audit log", scope, "b", source_id=spec, now=200)
    assert again["duplicate_of"] == first["fact_id"] and again["fact_id"] == first["fact_id"]
    assert again["sources_added"] == [spec]
    assert sources_of(client, graph, first["fact_id"]) == sorted([memo, spec])
    assert q(client, graph, "MATCH (f:Fact) RETURN count(f)") == [[1]]  # still one fact


def test_a_duplicate_reports_only_the_sources_it_did_not_have(client, graph, svc):
    eng, _, scope, memo, spec, third = svc
    first = eng.assert_fact("Rule C1", "requires", "audit log", scope, "a", source_ids=[memo, spec], now=100)
    again = eng.assert_fact(
        "Rule C1", "requires", "Audit  Log", scope, "b", source_ids=[spec, third, memo], now=200
    )
    assert again["duplicate_of"] == first["fact_id"]
    assert again["sources_added"] == [third]
    assert sources_of(client, graph, first["fact_id"]) == sorted([memo, spec, third])
    none = eng.assert_fact("Rule C1", "requires", "audit log", scope, "c", source_ids=[memo], now=300)
    assert none["duplicate_of"] == first["fact_id"] and none["sources_added"] == []
    bare = eng.assert_fact("Rule C1", "requires", "audit log", scope, "c", now=400)
    assert bare["duplicate_of"] == first["fact_id"] and bare["sources_added"] == []


def test_a_rejected_duplicate_assert_links_nothing(client, graph, svc):
    eng, _, scope, memo, spec, _ = svc
    first = eng.assert_fact("Rule C1", "requires", "audit log", scope, "a", source_id=memo, now=100)
    with pytest.raises(UnknownReference):
        eng.assert_fact("Rule C1", "requires", "audit log", scope, "b", source_ids=[spec, "nope"], now=200)
    assert sources_of(client, graph, first["fact_id"]) == [memo]


def test_a_new_value_does_not_inherit_the_old_facts_sources(client, graph, svc):
    eng, _, scope, memo, spec, _ = svc
    old = eng.assert_fact("Rule C1", "requires", "audit log", scope, "a", source_ids=[memo, spec], now=100)
    new = eng.assert_fact("Rule C1", "requires", "audit log v2", scope, "a", source_id=memo, now=200)
    assert new["duplicate_of"] is None and new["superseded"] == [old["fact_id"]]
    assert sources_of(client, graph, new["fact_id"]) == [memo]
    assert sources_of(client, graph, old["fact_id"]) == sorted([memo, spec])


@pytest.mark.slow
def test_a_paraphrase_merge_corroborates_too(client, graph):
    eng, lin = Engram(client, graph, FastEmbedder()), Lineage(client, graph)
    scope = eng.create_scope("global", "global", now=1)
    memo, spec = lin.create_source("urn:memo", now=1), lin.create_source("urn:spec", now=1)
    first = eng.assert_fact(
        "Orders service", "setting", "timeout is 5 minutes", scope, "a", source_id=memo, now=1000
    )
    again = eng.assert_fact(
        "Orders service", "setting", "timeout is 300 seconds", scope, "b", source_id=spec, now=2000
    )
    assert again["duplicate_of"] == first["fact_id"]
    assert again["sources_added"] == [spec]
    assert sources_of(client, graph, first["fact_id"]) == sorted([memo, spec])
