from __future__ import annotations


def test_scope_isolation_and_inheritance(eng, glob):
    p = eng.create_scope("project", "p", inherits=[glob])
    q = eng.create_scope("project", "q", inherits=[glob])
    eng.assert_fact("Acme", "deploy day", "friday", p, "a1", now=1000)
    eng.assert_fact("Acme", "company motto", "ship small", glob, "a1", now=1000)
    eng.assert_fact("Acme", "billing tool", "stripe", q, "a1", now=1000)

    in_p = {r["value"] for r in eng.recall("Acme", p, k=10)}
    in_q = {r["value"] for r in eng.recall("Acme", q, k=10)}
    in_g = {r["value"] for r in eng.recall("Acme", glob, k=10)}
    assert in_p == {"friday", "ship small"}  # P's own + inherited global; not Q's fact
    assert in_q == {"stripe", "ship small"}
    assert in_g == {"ship small"}  # global does not see its children


def test_inheritance_is_transitive_up_to_three_hops(eng, glob):
    p = eng.create_scope("project", "p", inherits=[glob])
    u = eng.create_scope("user", "u", inherits=[p])
    eng.assert_fact("X", "fact one", "global-fact", glob, "a1", now=1)
    eng.assert_fact("X", "fact two", "project-fact", p, "a1", now=1)
    assert {r["value"] for r in eng.recall("X", u, k=10)} == {"global-fact", "project-fact"}


def test_k_limits_results_and_orders_nearest_first(eng, proj):
    for i, v in enumerate(["alpha one", "beta two", "gamma three", "delta four", "epsilon five"]):
        eng.assert_fact(f"Thing{i}", "label", v, proj, "a1", now=1000)
    got = eng.recall("gamma three", proj, k=3)
    assert len(got) == 3
    assert got[0]["value"] == "gamma three"
    scores = [g["score"] for g in got]
    assert scores == sorted(scores) or got[0]["score"] == min(scores)
    assert len(eng.recall("gamma three", proj, k=1)) == 1
    assert eng.recall("gamma three", proj, k=0) == []


def test_budget_truncation(eng, proj):
    for i in range(6):
        eng.assert_fact(f"Service{i}", "note", f"runs on port {8000 + i} with a long description " * 2, proj, "a1", now=10)
    full = eng.recall("runs on port", proj, k=6, budget_chars=10_000)
    assert len(full) == 6
    texts = [f["text"] for f in full]
    budget = len(texts[0]) + len(texts[1]) + 5
    cut = eng.recall("runs on port", proj, k=6, budget_chars=budget)
    assert [c["text"] for c in cut] == texts[:2]
    assert sum(len(c["text"]) for c in cut) <= budget
    # a budget smaller than the best hit still returns it, truncated
    tiny = eng.recall("runs on port", proj, k=6, budget_chars=10)
    assert len(tiny) == 1 and len(tiny[0]["text"]) <= 10


def test_recall_path_has_entity_scope_provenance_and_agent(eng, client, graph, proj):
    s = eng.start_session("a1", "planner")
    ep = eng.remember_episode(s, "user", "the api uses postgres")
    r = eng.assert_fact("Acme Notes API", "database", "postgres", proj, "a1", episode_id=ep, now=100)
    (hit,) = eng.recall("Acme Notes API database postgres", proj, k=3)
    assert hit["fact_id"] == r["fact_id"]
    assert hit["text"] == "Acme Notes API database: postgres"
    rels = {(p["rel"], p["id"]) for p in hit["path"]}
    assert ("ABOUT", r["entity_id"]) in rels
    assert ("IN_SCOPE", proj) in rels
    assert ("DERIVED_FROM", ep) in rels
    assert ("ASSERTED_BY", "a1") in rels
    assert next(p for p in hit["path"] if p["rel"] == "DERIVED_FROM")["label"] == "Episode"
    assert hit["via"] is None


def test_one_hop_expansion_boosts_sibling_facts_on_same_entity(eng, proj):
    eng.assert_fact("Acme", "owner", "alice", proj, "a1", now=10)
    eng.assert_fact("Acme", "database", "postgres", proj, "a1", now=10)
    eng.assert_fact("Zed", "owner", "carol", proj, "a1", now=10)
    eng.assert_fact("Zed", "tool", "hammer", proj, "a1", now=10)
    # Both "Acme database" and "Zed owner" share exactly one token with the query; the boost for being a
    # sibling of the best hit (same ABOUT entity) ranks the Acme fact above the Zed one.
    got = eng.recall("Acme owner alice", proj, k=2)
    assert [g["value"] for g in got] == ["alice", "postgres"]
    assert got[0]["via"] is None


def test_recall_ignores_quarantined_and_unknown_scope(eng, client, graph, proj):
    r = eng.assert_fact("Acme", "owner", "alice", proj, "a1", now=10)
    client.graph(graph).query("MATCH (f:Fact {id:$id}) SET f.status='quarantined'", {"id": r["fact_id"]})
    assert eng.recall("Acme owner", proj, k=5) == []
    assert eng.recall("Acme owner", proj, k=5, as_of=20) == []
    assert eng.recall("Acme owner", "no-such-scope", k=5) == []
