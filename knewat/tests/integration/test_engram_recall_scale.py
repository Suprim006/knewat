"""Recall under pressure (review findings P1-02, P1-10): decoys beyond the first vector fetch, caps."""

from __future__ import annotations

import pytest

import knewat.engram.service as svc

QUERY = "alpha beta gamma delta"


@pytest.fixture(params=["vector-only", "with-keywords"])
def mode(request, monkeypatch):
    """Run starvation tests once with the keyword fallback off, so the adaptive vector fetch must work."""
    if request.param == "vector-only":
        monkeypatch.setattr(svc, "MAX_KEYWORDS", 0)
    return request.param


def test_in_scope_fact_found_despite_100_nearer_out_of_scope_facts(eng, glob, mode):
    mine = eng.create_scope("project", "mine", inherits=[glob])
    other = eng.create_scope("project", "other", inherits=[glob])
    for i in range(100):  # every decoy shares 4 query words, the target only 2
        eng.assert_fact(f"Decoy{i}", "topic", f"{QUERY} {i}", other, "a1", now=10)
    target = eng.assert_fact("Target", "topic", "alpha beta", mine, "a1", now=10)
    got = eng.recall(QUERY, mine, k=3)
    assert [g["fact_id"] for g in got] == [target["fact_id"]]


def test_recall_still_returns_k_results_when_decoys_dominate(eng, glob, mode):
    mine = eng.create_scope("project", "mine", inherits=[glob])
    other = eng.create_scope("project", "other", inherits=[glob])
    for i in range(60):
        eng.assert_fact(f"Decoy{i}", "topic", f"{QUERY} {i}", other, "a1", now=10)
    ids = {
        eng.assert_fact(f"Mine{i}", "topic", f"alpha {i}", mine, "a1", now=10)["fact_id"] for i in range(5)
    }
    got = eng.recall(QUERY, mine, k=5)
    assert {g["fact_id"] for g in got} == ids


def test_active_fact_found_behind_many_nearer_superseded_versions(eng, proj, mode):
    for i in range(30):  # older versions mention more query words, so they rank nearer than the active one
        eng.assert_fact("Acme", "notes", f"{QUERY} epsilon zeta {i}", proj, "solo", now=100 + i)
    active = eng.assert_fact("Acme", "notes", "alpha", proj, "solo", now=500)
    got = eng.recall(QUERY, proj, k=1)
    assert [g["fact_id"] for g in got] == [active["fact_id"]]
    assert got[0]["status"] == "active"
    # as_of in the past finds the version valid then, not nothing
    past = eng.recall(QUERY, proj, k=1, as_of=115)
    assert len(past) == 1 and past[0]["value"].endswith(" 15")


def test_without_adaptive_fetch_or_keywords_decoys_do_starve_the_target(eng, glob, monkeypatch):
    """Documents the FalkorDB limitation (no vector pre-filter) that the adaptive fetch works around."""
    mine = eng.create_scope("project", "mine", inherits=[glob])
    other = eng.create_scope("project", "other", inherits=[glob])
    for i in range(30):
        eng.assert_fact(f"Decoy{i}", "topic", f"{QUERY} {i}", other, "a1", now=10)
    eng.assert_fact("Target", "topic", "alpha beta", mine, "a1", now=10)
    monkeypatch.setattr(svc, "MAX_KEYWORDS", 0)
    monkeypatch.setattr(svc, "MAX_OVER", 12)  # = k * OVERFETCH: no widening possible
    assert eng.recall(QUERY, mine, k=3) == []


def test_keyword_fallback_finds_an_exact_word_beyond_the_vector_cap(eng, glob, monkeypatch):
    mine = eng.create_scope("project", "mine", inherits=[glob])
    other = eng.create_scope("project", "other", inherits=[glob])
    for i in range(40):
        eng.assert_fact(f"Decoy{i}", "topic", f"{QUERY} {i}", other, "a1", now=10)
    target = eng.assert_fact("Target", "topic", "zebrafish", mine, "a1", now=10)
    monkeypatch.setattr(svc, "MAX_OVER", 8)  # the vector side can no longer reach the target
    got = eng.recall(f"{QUERY} zebrafish", mine, k=1)
    assert [g["fact_id"] for g in got] == [target["fact_id"]]


def test_query_of_only_special_characters_or_stopwords_does_not_error(eng, proj):
    eng.assert_fact("Acme", "owner", "alice", proj, "a1", now=10)
    assert isinstance(eng.recall("(((*) [] {} ~ -", proj, k=3), list)
    assert isinstance(eng.recall("the of a", proj, k=3), list)
    assert isinstance(eng.recall("", proj, k=3), list)


def test_k_and_budget_are_clamped(eng, proj, monkeypatch):
    seen = []
    real = eng.client.ro

    def spy(graph, name, params=None):
        if name == "engram/recall":
            seen.append(params)
        return real(graph, name, params)

    monkeypatch.setattr(eng.client, "ro", spy)
    eng.assert_fact("Acme", "owner", "alice", proj, "a1", now=10)
    # retrieval only: with separation on, "Acme" names an entity whose facts join the candidates
    got = eng.recall("Acme", proj, k=10_000, budget_chars=10_000_000, forgetting=False, separation=False)
    assert len(got) <= svc.MAX_K == 50
    # P12: the candidate pool is max(3k, 60) capped at MAX_POOL (150), plus every keyword hit
    assert all(p["lim"] - len(p["kw_ids"]) == svc.MAX_POOL == 150 for p in seen)
    assert svc.MAX_BUDGET_CHARS == 20_000
    assert all(p["over"] <= svc.MAX_OVER for p in seen)
    seen.clear()
    eng.recall("Acme", proj, k=10_000, budget_chars=10_000_000, forgetting=True)
    assert all(p["lim"] - len(p["kw_ids"]) == svc.MAX_POOL for p in seen)
    assert all(p["over"] <= svc.MAX_OVER for p in seen)


def test_budget_is_clamped_to_20000_chars(eng, proj):
    for i in range(30):
        eng.assert_fact(f"Svc{i}", "note", "long " * 400, proj, "a1", now=10)
    got = eng.recall("long", proj, k=50, budget_chars=10_000_000)
    assert sum(len(g["text"]) for g in got) <= 20_000
    assert len(got) < 30  # the cap cut the list


def test_sibling_expansion_is_capped_per_seed(eng, client, graph, proj):
    for i in range(30):
        eng.assert_fact("Hot", f"attr{i}", f"value {i}", proj, "a1", now=10)
    params = {
        "q": eng.embedder.embed(["Hot attr3 value 3"])[0],
        "scope_id": proj,
        "over": 1,  # exactly one seed
        "lim": 50,
        "all": False,
        "t": 20,
        "statuses": ["active"],
        "boost": 0.05,
        "sibs": 5,
        "kw_ids": [],
        "damp": False,
        "smax": 3.912,
    }
    rows = client.ro(graph, "engram/recall", params)
    assert len(rows) == 6  # 1 seed + 5 siblings, not 30
    assert sum(1 for r in rows if r["via"] is None) == 1
    # the siblings kept are the nearest ones, not an arbitrary 5
    sib_dist = sorted(r["score"] for r in rows if r["via"] is not None)
    all_rows = client.ro(graph, "engram/recall", {**params, "sibs": 100})
    all_sib = sorted(r["score"] for r in all_rows if r["via"] is not None)
    assert sib_dist == all_sib[:5]


@pytest.mark.parametrize("bad", [0, -3])
def test_nonpositive_k_returns_empty(eng, proj, bad):
    assert eng.recall("anything", proj, k=bad) == []
