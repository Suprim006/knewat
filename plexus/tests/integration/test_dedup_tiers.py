"""B0/B1/B2 end to end with the real embedder: guards, the Jaccard second tier, soft links, reversible wording."""

# ruff: noqa: E501 - long literal tables and prose lines

from __future__ import annotations

import pytest

from plexus.embed import FastEmbedder
from plexus.engram import Engram

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def fast() -> FastEmbedder:
    return FastEmbedder()


@pytest.fixture
def feng(client, graph, fast) -> Engram:
    return Engram(client, graph, fast)


@pytest.fixture
def fscope(feng):
    return feng.create_scope("global", "global")


def _facts(client, graph) -> int:
    return client.graph(graph).ro_query("MATCH (f:Fact) RETURN count(f)").result_set[0][0]


def _two(feng, scope, a, b, predicate="setting", agent2="a1"):
    r1 = feng.assert_fact("Orders service", predicate, a, scope, "a1", now=1000)
    r2 = feng.assert_fact("Orders service", predicate, b, scope, agent2, now=2000)
    return r1, r2


# B0: the PRODUCT_FIXES B.1 failure list. Today every one of these is auto-merged and the second statement vanishes.
HOSTILE = [
    ("The cache is enabled", "The cache is not enabled in staging"),
    ("Retries are enabled", "Retries are disabled for the orders queue"),
    ("Feature flag is on", "Feature flag is off for all users"),
    ("Latency must stay below 200 ms", "Latency must stay above 200 ms"),
    ("Retries at least 3", "Retries at most 3 times"),
    ("deploys need two reviewers", "deploys need three reviewers"),
    ("timeout is 5 minutes", "timeout is 5 hours"),
    ("Service A calls B", "Service B calls A"),
]


@pytest.mark.parametrize(("a", "b"), HOSTILE)
def test_hostile_pairs_are_never_merged(feng, client, graph, fscope, a, b):
    r1, r2 = _two(feng, fscope, a, b)
    assert r2["duplicate_of"] is None, (a, b)
    assert r2["fact_id"] != r1["fact_id"]
    assert _facts(client, graph) == 2  # nothing was thrown away: the old value is superseded, not lost


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("timeout is 5 minutes", "timeout is 300 seconds"),
        ("Owns it.", "Owns it"),
        ("two reviewers must approve", "2 reviewers must approve"),
    ],
)
def test_same_quantity_or_punctuation_still_merges(feng, client, graph, fscope, a, b):
    r1, r2 = _two(feng, fscope, a, b, agent2="a2")
    assert r2["duplicate_of"] == r1["fact_id"], (a, b)
    assert _facts(client, graph) == 1


def test_merged_wording_is_kept_on_the_asserted_by_edge(feng, client, graph, fscope):
    r1, _ = _two(feng, fscope, "timeout is 5 minutes", "timeout is 300 seconds", agent2="a2")
    rows = (
        client.graph(graph)
        .ro_query(
            "MATCH (:Fact {id:$f})-[r:ASSERTED_BY]->(a:Agent {id:'a2'}) RETURN r.text", {"f": r1["fact_id"]}
        )
        .result_set
    )
    assert rows == [["timeout is 300 seconds"]]


# B1: the three heavy paraphrases the 0.08 cosine threshold missed (tier 2: Jaccard AND cos <= 0.16, keys equal)
@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("deploys need two reviewers", "two reviewers must approve every production deploy"),
        ("on-call engineer is paged first", "first to be paged is whoever is on call"),
    ],
)
def test_heavy_paraphrase_is_a_duplicate_or_at_least_a_soft_link(feng, client, graph, fscope, a, b):
    r1, r2 = _two(feng, fscope, a, b, agent2="a2")
    if r2["duplicate_of"] is None:
        assert [m["fact_id"] for m in r2["possible_duplicates"]] == [r1["fact_id"]]
    else:
        assert r2["duplicate_of"] == r1["fact_id"]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Written in Go", "Written in Rust"),
        ("Runs on Mondays", "Runs on Fridays"),
        ("Hosted in eu-west", "Hosted in us-east"),
        ("Retries 3", "5 times"),
    ],
)
def test_controls_are_not_duplicates(feng, client, graph, fscope, a, b):
    _, r2 = _two(feng, fscope, a, b)
    assert r2["duplicate_of"] is None


# B2
def test_clearly_different_values_get_no_soft_link(feng, fscope):
    _, r2 = _two(feng, fscope, "Written in Go", "Hosted in eu-west", predicate="note")
    assert r2["possible_duplicates"] == []


def test_swapped_direction_gets_a_soft_link_and_a_new_fact(feng, client, graph, fscope):
    r1, r2 = _two(feng, fscope, "Service A calls B", "Service B calls A", agent2="a2")
    assert r2["duplicate_of"] is None
    assert [m["fact_id"] for m in r2["possible_duplicates"]] == [r1["fact_id"]]
    link = (
        client.graph(graph)
        .ro_query(
            "MATCH (n:Fact {id:$n})-[l:DUPLICATES_MAYBE]->(o:Fact {id:$o}) RETURN l.score, l.cos, l.jaccard",
            {"n": r2["fact_id"], "o": r1["fact_id"]},
        )
        .result_set
    )
    assert len(link) == 1 and link[0][2] == 1.0  # same words, other order
