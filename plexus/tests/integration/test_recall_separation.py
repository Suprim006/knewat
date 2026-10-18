"""D-013 P1: pattern separation at recall against a real FalkorDB.

The embedder puts a fact at an exact cosine distance from the query: a value containing ``~0.30`` is 0.30
away from any text containing ``QUERY``, so relevance is exact and only the entity lift can change the order.
The query text also names the entity ("Acme Notes API S07 ... QUERY"), which is what the entity read resolves.
Every fact carries a marker: with dozens of hashed (exactly orthogonal) vectors the HNSW index failed to
navigate to the two nearest nodes at all (an artefact of the degenerate test space, seen while writing this).
"""

from __future__ import annotations

import hashlib
import math
import re

import pytest
from tests.plan_util import BIG, max_records, profile_ops, seed_big_scope

from plexus.activation import Activation, Settings
from plexus.activation import score as S
from plexus.embed import HashEmbedder
from plexus.embed.base import DIM
from plexus.engram import Engram
from plexus.engram import service as svc
from plexus.lineage import Lineage

WE, WP = S.W_ENTITY_DEFAULT, S.W_PREDICATE_DEFAULT
_MARK = re.compile(r"~(\d+\.\d+)")


class NamingEmbedder:
    """``QUERY`` in the text -> e0; ``~d`` -> a unit vector at cosine distance d from e0; else hashed."""

    def __init__(self) -> None:
        self.dim = DIM
        self._h = HashEmbedder()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        if "QUERY" in text:
            return [1.0] + [0.0] * (DIM - 1)
        m = _MARK.search(text)
        if not m:
            return self._h.embed([text])[0]
        cos = 1.0 - float(m.group(1))
        j = 1 + int.from_bytes(hashlib.md5(text.encode(), usedforsecurity=False).digest()[:4], "little") % (
            DIM - 1
        )
        v = [0.0] * DIM
        v[0], v[j] = cos, math.sqrt(max(0.0, 1.0 - cos * cos))
        return v


@pytest.fixture
def eng(client, graph) -> Engram:
    return Engram(client, graph, NamingEmbedder())


@pytest.fixture
def scope(eng) -> str:
    return eng.create_scope("global", "global", now=1)


def ids(rows):
    return [r["fact_id"] for r in rows]


@pytest.fixture
def twins(eng, scope):
    """S07 target at 0.30, its S08 twin NEARER at 0.29, and one sibling (another predicate, 0.40) each."""
    target = eng.assert_fact("Acme Notes API S07", "api_version", "v14 ~0.30", scope, "alice", now=1000)[
        "fact_id"
    ]
    twin = eng.assert_fact("Acme Notes API S08", "api_version", "v16 ~0.29", scope, "alice", now=1001)[
        "fact_id"
    ]
    sib = eng.assert_fact("Acme Notes API S07", "database", "pg ~0.40", scope, "alice", now=1002)["fact_id"]
    sib8 = eng.assert_fact("Acme Notes API S08", "database", "my ~0.40", scope, "alice", now=1003)["fact_id"]
    return target, twin, sib, sib8


Q = "Acme Notes API S07 api_version QUERY"


def test_the_named_entity_wins_over_a_nearer_twin_and_both_switches_off_keep_the_plain_order(
    eng, scope, twins
):
    target, twin, sib, sib8 = twins
    plain = eng.recall(Q, scope, k=4, forgetting=False, separation=False)
    assert ids(plain)[:2] == [twin, target], "nearer wins; both get the same sibling boost"
    assert all(r["entity_match"] is None and r["sep"] is None and r["lures"] == [] for r in plain)
    got, meta = eng.recall_with_meta(Q, scope, k=3, forgetting=False, separation=True)
    assert ids(got) == [target, twin, sib], (
        "the named entity's fact with the named predicate first (both cues); the nearer twin (predicate cue "
        "only) keeps its place above the far sibling (entity cue only): at the shipped weights the cues "
        "decide near-ties, not the order of facts 0.1 apart"
    )
    assert list(meta["entities"]) and all(
        e["name"] == "Acme Notes API S07" for e in meta["entities"].values()
    )
    e = next(iter(meta["entities"].values()))
    assert e["fan"] == 2, "two current facts about S07 in the scope"
    assert meta["predicates"] == {"api_version": {"fan": 2}}, "the query names api_version: S07's and S08's"
    assert meta["entity_facts_added"] == 0, "S07's facts were already candidates"
    by = {r["fact_id"]: r for r in got}
    assert by[target]["entity_match"] is True and by[target]["predicate_match"] is True
    assert by[target]["sep"] == pytest.approx((WE + WP) * (5 - math.log(2)))
    assert by[sib]["entity_match"] is True and by[sib]["predicate_match"] is False
    assert by[sib]["sep"] == pytest.approx(WE * (5 - math.log(2)))
    assert by[twin]["entity_match"] is False and by[twin]["predicate_match"] is True
    assert by[twin]["sep"] == pytest.approx(WP * (5 - math.log(2)))
    # the single-cue form P1 first shipped: the predicate is not a cue, the twin gets nothing
    one, _ = eng.recall_with_meta(
        Q, scope, k=3, forgetting=False, separation=True, settings=Settings(cues="entity")
    )
    assert ids(one) == [target, twin, sib]
    by1 = {r["fact_id"]: r for r in one}
    assert by1[target]["sep"] == pytest.approx(0.15 * (1 - math.log(2) / math.log(50)))
    assert by1[twin]["sep"] == 0.0, "the match is reported, the single-cue form gives it no weight"
    assert by[target]["lures"] == [twin] and by[twin]["lures"] == [target], (
        "same predicate, other entity, 0.01 apart"
    )
    assert by[sib]["lures"] == [sib8]


def test_the_twin_is_not_resolved_as_a_named_entity(eng, scope, twins):
    ents = eng._resolve_entities(Q, scope, 10_000, ["active"])
    assert [e["name"] for e in ents.values()] == ["Acme Notes API S07"]
    assert eng._resolve_entities("api_version QUERY", scope, 10_000, ["active"]) == {}
    # the exact norm_name pass finds an entity whose words the full-text OR also returns
    ents = eng._resolve_entities("acme   notes API s08", scope, 10_000, ["active"])
    assert [e["name"] for e in ents.values()] == ["Acme Notes API S08"] and next(iter(ents.values()))[
        "fan"
    ] == 2


def test_separation_works_with_forgetting_on_in_both_modes(eng, scope, twins):
    target, twin, sib, sib8 = twins
    for mode in ("mult", "add"):
        got = eng.recall(Q, scope, k=3, settings=Settings(act_mode=mode), forgetting=True, separation=True)
        assert ids(got)[0] == target, mode
        assert got[0]["activation"] is not None and got[0]["salience"] == 0.0


def test_a_hub_entity_gets_no_lift(eng, scope):
    for i in range(50):
        eng.assert_fact("Hub Service", f"setting_{i}", f"value {i} ~0.90", scope, "alice", now=1000 + i)
    target = eng.assert_fact("Hub Service", "api_version", "v1 ~0.30", scope, "alice", now=2000)["fact_id"]
    twin = eng.assert_fact("Other Service", "api_version", "v2 ~0.29", scope, "alice", now=2001)["fact_id"]
    got, meta = eng.recall_with_meta("Hub Service api_version QUERY", scope, k=2, forgetting=False)
    assert next(iter(meta["entities"].values()))["fan"] == 51
    # two cues (CROSS_CHECK §3.2): a fan of 51 still lifts a little (S = 5 > ln 51), and both candidates get
    # the predicate cue, so the hub's own api_version fact wins although the twin is nearer
    assert ids(got) == [target, twin]
    assert got[0]["entity_match"] is True and got[0]["sep"] == pytest.approx(
        WE * (5 - math.log(51)) + WP * (5 - math.log(2))
    )
    assert got[1]["entity_match"] is False and got[1]["sep"] == pytest.approx(WP * (5 - math.log(2)))
    # the single-cue form: fan >= 50 lifts nothing, relevance decides
    one = eng.recall(
        "Hub Service api_version QUERY", scope, k=2, forgetting=False, settings=Settings(cues="entity")
    )
    assert ids(one) == [twin, target], "fan >= 50: relevance decides"
    assert one[1]["entity_match"] is True and one[1]["sep"] == 0.0


def test_why_recalled_stores_the_entities_the_separation_flag_and_the_lift(eng, scope, twins, client, graph):
    target, twin, sib, sib8 = twins
    hits, meta = eng.recall_with_meta(Q, scope, k=3, forgetting=False)
    lin = Lineage(client, graph)
    rid = lin.record_recall(
        "alice", None, Q, scope, 3, hits, entities=sorted(meta["entities"]), separation=True
    )
    why = lin.why_recalled(rid)
    assert why["recall"]["separation"] is True and why["recall"]["entities"] == sorted(meta["entities"])
    seps = {r["fact_id"]: r["sep"] for r in why["results"]}
    assert seps[target] > seps[sib] > seps[twin] > 0, "both cues > entity cue > predicate cue (same fan 2)"
    edge = next(e for e in why["edges"] if e["rel"] == "RETURNED" and e["to"] == target)
    assert edge["props"]["sep"] == pytest.approx(seps[target])
    # a recall recorded without the D-013 arguments reads back with the defaults
    rid0 = lin.record_recall("alice", None, "q", scope, 1, [{"fact_id": target}])
    w0 = lin.why_recalled(rid0)
    assert (
        w0["recall"]["separation"] is False
        and w0["recall"]["entities"] == []
        and w0["results"][0]["sep"] == 0.0
    )


def test_memory_strength_reports_salience_fan_and_entity_lift(eng, scope, twins, client, graph):
    target, _, _, _ = twins
    s = Activation(client, graph, Settings(act_mode="add")).strength(target)
    assert s is not None
    assert s["mode"] == "add" and s["fan"] == 2 and s["entity_lift"] == pytest.approx(WE * (5 - math.log(2)))
    assert s["salience"] == 0.0 and s["suggested_verify_after"] is None and -0.05 <= s["act_term"] <= 0.05
    assert s["decays"] and all(0 < d <= 1.0 for d in s["decays"])


# -- plan shape: the entity read must not enumerate the scope ------------------------------------------


def test_recall_entities_is_an_index_seek_not_a_scope_scan(client, graph):
    seed_big_scope(client, graph)
    params = {"q": "e1|entity", "scope_id": "S", "all": False, "limit": 5, "statuses": ["active"], "t": 5}
    ops = profile_ops(client, graph, "engram/recall_entities", params)
    worst = max_records(ops)
    assert worst.records < BIG, f"scope-wide enumeration: {worst}\n" + "\n".join(map(str, ops))


def test_recall_predicates_is_an_index_seek_not_a_scope_scan(client, graph):
    seed_big_scope(client, graph)
    params = {"predicates": ["p", "nothing"], "scope_id": "S", "all": False, "statuses": ["active"], "t": 5}
    rows = {r["predicate"]: r["fan"] for r in client.ro(graph, "engram/recall_predicates", params)}
    assert rows == {"p": BIG, "nothing": 0}, "one row per input predicate, fan 0 when none"
    assert client.ro(graph, "engram/recall_predicates", {**params, "predicates": []}) == []
    ops = profile_ops(client, graph, "engram/recall_predicates", {**params, "predicates": ["nothing"]})
    worst = max_records(ops)
    assert worst.records < BIG, f"scope-wide enumeration: {worst}\n" + "\n".join(map(str, ops))


# -- CROSS_CHECK §3.3: the named entity's own facts join the candidates -----------------------------


def test_the_named_entitys_facts_join_the_candidates_when_the_vector_fetch_misses_them(
    eng, scope, monkeypatch
):
    """Fifty near facts about other entities crowd the named entity's far fact out of the over-fetch
    (the pool is shrunk to 6 so the vector fetch is 24 nodes; since P12 the default pool of 60 would reach all
    of them); with separation on the entity read adds it and the two cues rank it first."""
    monkeypatch.setattr(svc, "MIN_POOL", 2)
    # P12's keyword channel also matches the entity name and would find the fact: isolate the vector side
    monkeypatch.setattr(eng, "_keyword_ids", lambda *a, **k: [])
    for i in range(50):
        eng.assert_fact(
            f"Other Thing {i}", "api_version", f"v{i} ~0.{58 + i % 3}", scope, "alice", now=1000 + i
        )
    target = eng.assert_fact("Lonely Service", "api_version", "v7 ~0.62", scope, "alice", now=2000)["fact_id"]
    q = "Lonely Service api_version QUERY"
    plain = eng.recall(q, scope, k=2, forgetting=False, separation=False)
    assert target not in ids(plain), "the vector fetch stops at the 24 nearest in-scope facts"
    got, meta = eng.recall_with_meta(q, scope, k=2, forgetting=False, separation=True)
    assert meta["entity_facts_added"] == 1 and ids(got)[0] == target
    assert got[0]["entity_match"] is True and got[0]["predicate_match"] is True
    assert got[0]["via"] is None and got[0]["score"] == pytest.approx(0.62, abs=1e-3)


# -- merged with P12: the pool and scope 'all' next to the D-013 terms ----------------------


def test_the_python_sibling_boost_keeps_the_fan_damping(eng, scope):
    """P12 re-applies the sibling boost in Python (``_sibling_boost``); the D-013 fan damping must survive
    that: the Cypher returns the entity's damp factor per row and the Python boost is scaled by it."""
    for i in range(60):
        eng.assert_fact("Hub Service", f"setting_{i}", f"value {i} ~0.90", scope, "alice", now=1000 + i)
    eng.assert_fact("Hub Service", "api_version", "v1 ~0.30", scope, "alice", now=2000)
    q = eng._embed_query("Hub Service api_version QUERY")
    args = (q, scope, 6, 10_000, ["active"], [], False)
    damped = eng._fetch_candidates(*args, damp=True, smax=math.log(50))
    plain = eng._fetch_candidates(*args, damp=False, smax=math.log(50))
    assert all(r["damp"] == 0.0 for r in damped) and all(r["damp"] == 1.0 for r in plain)
    svc._sibling_boost(damped, 1)
    svc._sibling_boost(plain, 1)
    assert all(r["rank"] == pytest.approx(r["score"]) for r in damped), "fan 61 >= 50: no sibling boost"
    boosted = [r for r in plain if r["rank"] < r["score"]]
    assert boosted and all(r["rank"] == pytest.approx(r["score"] - svc.EXPAND_BOOST) for r in boosted)


def test_all_scopes_counts_the_fans_over_every_scope(eng, scope):
    proj = eng.create_scope("project", "p1", inherits=[scope])
    other = eng.create_scope("project", "p2", inherits=[scope])
    eng.assert_fact("Acme Notes API S07", "api_version", "v14 ~0.30", scope, "alice", now=1000)
    eng.assert_fact("Acme Notes API S07", "database", "pg ~0.40", proj, "alice", now=1001)
    eng.assert_fact("Acme Notes API S07", "cache", "redis ~0.45", other, "alice", now=1002)
    scoped, meta = eng.recall_with_meta(Q, proj, k=5)
    assert next(iter(meta["entities"].values()))["fan"] == 2, "global + p1, not p2"
    everywhere, meta = eng.recall_with_meta(Q, scope, k=5, all_scopes=True)
    assert next(iter(meta["entities"].values()))["fan"] == 3, "scope 'all': every scope counts"
    assert meta["entity_facts_added"] >= 0 and len(everywhere) == 3 and len(scoped) == 2
    assert meta["predicates"] == {"api_version": {"fan": 1}}
