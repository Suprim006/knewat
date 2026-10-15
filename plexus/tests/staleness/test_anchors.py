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
