"""P7-int: ``Source.trust`` is the string 'normal' | 'high'. A number (legacy) means 'normal'."""

from __future__ import annotations

import pytest

from .conftest import cypher


def trust_of(client, graph, source_id):
    return cypher(client, graph, "MATCH (s:Source {id:$i}) RETURN s.trust", i=source_id)[0][0]


def test_default_is_normal(lin, client, graph):
    assert trust_of(client, graph, lin.create_source("https://a.example/x")) == "normal"


@pytest.mark.parametrize("legacy", [1.0, 0.1, 0, 1])
def test_a_number_means_normal(lin, client, graph, legacy):
    assert trust_of(client, graph, lin.create_source("https://a.example/x", trust=legacy)) == "normal"


def test_high_is_stored_and_a_default_or_numeric_refresh_does_not_demote_it(lin, client, graph):
    sid = lin.create_source("https://a.example/x", trust="high")
    assert trust_of(client, graph, sid) == "high"
    lin.create_source("https://a.example/x")  # kind/title refresh with no opinion on trust
    lin.create_source("https://a.example/x", trust=1.0)
    assert trust_of(client, graph, sid) == "high"
    lin.create_source("https://a.example/x", trust="normal")  # an explicit change is honoured
    assert trust_of(client, graph, sid) == "normal"


def test_trust_is_case_insensitive_and_anything_else_is_rejected(lin, client, graph):
    assert trust_of(client, graph, lin.create_source("https://a.example/x", trust=" HIGH ")) == "high"
    with pytest.raises(ValueError, match="trust"):
        lin.create_source("https://a.example/y", trust="very")
    assert cypher(client, graph, "MATCH (s:Source {uri:'https://a.example/y'}) RETURN count(s)") == [[0]]


def test_a_legacy_float_source_is_migrated_to_normal_when_it_is_next_written(lin, client, graph):
    cypher_write = client.graph(graph).query
    cypher_write(
        "CREATE (:Source {id:'old', uri:'https://old.example', kind:'doc', trust:1.0, created_at:1})"
    )
    assert lin.create_source("https://old.example") == "old"
    assert trust_of(client, graph, "old") == "normal"
