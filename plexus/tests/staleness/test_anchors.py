"""Slice 1: CodeAnchor upsert, ``anchor_fact`` and ``describe_code``."""

from __future__ import annotations

import pytest

from plexus.codescan.paths import anchor_id

from .conftest import cypher

P = "C:/repo/app/payments.py"


def _anchors(client, graph):
    return cypher(
        client,
        graph,
        "MATCH (a:CodeAnchor) RETURN a.id, a.path, a.symbol, a.kind, a.hash, a.repo ORDER BY a.id",
    )


def test_anchor_fact_creates_anchor_and_edge(stale, mem, client, graph):
    f = mem.fact("timeout", "30 seconds")
    out = stale.anchor_fact(f, "c:\\repo\\app\\payments.py", hash="h1")
    assert out["anchor_id"] == anchor_id(P) and out["path"] == P and out["symbol"] == ""
    assert _anchors(client, graph) == [[anchor_id(P), P, "", "file", "h1", ""]]
    assert cypher(
        client, graph, "MATCH (:Fact {id:$f})-[r:ANCHORED_TO]->(a:CodeAnchor) RETURN a.id, r.at", f=f
    ) == [[anchor_id(P), 1_000_000]]


def test_anchor_fact_with_symbol_is_a_function_or_class_anchor(stale, mem, client, graph):
    f = mem.fact("timeout", "30 seconds")
    stale.anchor_fact(f, P, symbol="PaymentService.create", hash="h2")
    row = _anchors(client, graph)[0]
    assert row[0] == anchor_id(P, "PaymentService.create") and row[2] == "PaymentService.create"
    assert row[3] == "function"
    stale.anchor_fact(f, P, symbol="PaymentService", kind="class")
    assert sorted(r[3] for r in _anchors(client, graph)) == ["class", "function"]


def test_anchor_fact_is_idempotent_and_shares_the_anchor(stale, mem, client, graph, clock):
    f1, f2 = mem.fact("timeout", "30 seconds"), mem.fact("retries", "3")
    stale.anchor_fact(f1, P, hash="h1")
    clock.advance(10)
    stale.anchor_fact(f1, P, hash="h1")
    stale.anchor_fact(f2, P)
    assert len(_anchors(client, graph)) == 1
    n = cypher(client, graph, "MATCH (:Fact)-[r:ANCHORED_TO]->(:CodeAnchor) RETURN count(r)")[0][0]
    assert n == 2
    # an anchor that is already tracked keeps its hash: only mark_changed moves it afterwards
    stale.anchor_fact(f2, P, hash="other")
    assert _anchors(client, graph)[0][4] == "h1"


def test_anchor_fact_fills_an_empty_hash(stale, mem, client, graph):
    f = mem.fact("timeout", "30 seconds")
    stale.anchor_fact(f, P)
    assert _anchors(client, graph)[0][4] == ""
    stale.anchor_fact(f, P, hash="h9")
    assert _anchors(client, graph)[0][4] == "h9"


def test_anchor_fact_unknown_fact_raises_and_writes_nothing(stale, client, graph):
    with pytest.raises(LookupError):
        stale.anchor_fact("no-such-fact", P, hash="h1")
    assert _anchors(client, graph) == []


def test_anchor_fact_rejects_a_relative_path_and_a_bad_kind(stale, mem, client, graph):
    f = mem.fact("timeout", "30 seconds")
    with pytest.raises(ValueError):
        stale.anchor_fact(f, "app/payments.py")
    with pytest.raises(ValueError):
        stale.anchor_fact(f, P, symbol="f", kind="module")
    assert _anchors(client, graph) == []


def test_describe_code_links_a_source_to_an_anchor(stale, mem, client, graph):
    doc = mem.source("C:/repo/docs/payments.md")
    out = stale.describe_code(doc, P, symbol="PaymentService.create", hash="h2")
    assert out["anchor_id"] == anchor_id(P, "PaymentService.create")
    assert cypher(
        client, graph, "MATCH (s:Source {id:$s})-[r:DESCRIBES]->(a:CodeAnchor) RETURN a.id, r.at", s=doc
    ) == [[anchor_id(P, "PaymentService.create"), 1_000_000]]


def test_describe_code_unknown_source_raises_and_writes_nothing(stale, mem, client, graph):
    f = mem.fact("timeout", "30 seconds")  # a fact id is not a source id
    with pytest.raises(LookupError):
        stale.describe_code(f, P)
    with pytest.raises(LookupError):
        stale.describe_code("nope", P)
    assert _anchors(client, graph) == []


# -- P7-13: a hash that differs from the stored one proves the fact was verified against older code -------
def _state(client, graph, fid):
    return cypher(
        client,
        graph,
        "MATCH (f:Fact {id:$f}) RETURN coalesce(f.verify_state,'verified'), coalesce(f.suspect_since,0)",
        f=fid,
    )[0]


def test_anchor_fact_with_an_older_hash_makes_the_fact_suspect(stale, mem, client, graph, clock):
    f1, f2 = mem.fact("timeout", "30 seconds"), mem.fact("retries", "3")
    stale.anchor_fact(f1, P, hash="h1")  # the server's hash for the file
    clock.advance(500)
    out = stale.anchor_fact(f2, P, hash="h0")  # f2 was checked against h0, an older version
    assert out["suspect"] is True and out["hash"] == "h1" and out["change_id"]
    assert _state(client, graph, f2) == ["suspect", 1_000_500]
    assert _state(client, graph, f1) == ["verified", 0]  # the other fact on the anchor is not touched
    (row,) = stale.facts_to_verify()
    assert row["fact_id"] == f2 and row["reason"] == f"changed in working tree ({P})"
    assert row["change"]["change_id"] == out["change_id"]
    # the stored hash is still the server's, and no doc is told that code changed
    assert _anchors(client, graph)[0][4] == "h1"
    assert cypher(client, graph, "MATCH (:Change)-[:TOUCHED]->(:CodeAnchor) RETURN count(*)") == [[0]]


def test_anchor_fact_hash_mismatch_is_idempotent(stale, mem, client, graph, clock):
    f1, f2 = mem.fact("timeout", "30 seconds"), mem.fact("retries", "3")
    stale.anchor_fact(f1, P, hash="h1")
    clock.advance(500)
    first = stale.anchor_fact(f2, P, hash="h0")
    clock.advance(500)
    again = stale.anchor_fact(f2, P, hash="h0")
    assert again["change_id"] == first["change_id"]
    assert cypher(client, graph, "MATCH (c:Change) RETURN count(c)") == [[1]]
    assert _state(client, graph, f2) == ["suspect", 1_000_500]  # the first suspicion time is kept


@pytest.mark.parametrize(
    ("stored", "given"),
    [("h1", "h1"), ("h1", ""), ("", "h0")],
    ids=["same hash", "no hash given", "nothing stored yet"],
)
def test_anchor_fact_without_a_conflicting_hash_marks_nothing(stale, mem, client, graph, stored, given):
    f1, f2 = mem.fact("timeout", "30 seconds"), mem.fact("retries", "3")
    stale.anchor_fact(f1, P, hash=stored)
    out = stale.anchor_fact(f2, P, hash=given)
    assert "suspect" not in out
    assert _state(client, graph, f2) == ["verified", 0]
    assert cypher(client, graph, "MATCH (c:Change) RETURN count(c)") == [[0]]
