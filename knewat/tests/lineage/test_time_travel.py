from __future__ import annotations

import pytest

from plexus.lineage import UnknownNode

from .conftest import cypher


# -- why_recalled ---------------------------------------------------------------------------------------
def test_why_recalled_matches_the_recall_results_and_ranks(world, lin):
    w = world
    res = lin.why_recalled(w.recall1)
    assert res["recall"] == {
        "id": w.recall1,
        "query": w.q1,
        "at": 3000,
        "k": 8,
        "scope_id": w.proj,
        "agent_id": "planner",
        "step": {"id": w.p1, "n": 1, "at": 3000},
        "entities": [],
        "separation": False,
    }
    assert [(r["rank"], r["fact_id"]) for r in res["results"]] == [
        (i, r["fact_id"]) for i, r in enumerate(w.results1, 1)
    ]
    assert [r["score"] for r in res["results"]] == pytest.approx([r["score"] for r in w.results1])
    assert res["truncated"] is False


def test_why_recalled_provenance_of_each_fact(world, lin):
    w = world
    by_fact = {r["fact_id"]: r for r in lin.why_recalled(w.recall1)["results"]}
    db1 = by_fact[w.db1]
    assert db1["entity"]["name"] == "Acme Notes API"
    assert db1["asserted_by"] == ["researcher"]
    assert sorted(d["id"] for d in db1["derived_from"]) == sorted([w.good, w.ep])
    assert {d["label"] for d in db1["derived_from"]} == {"Source", "Episode"}
    assert db1["scope"]["id"] == w.proj
    assert db1["props"]["value"] == "PostgreSQL 16"
    assert [d["id"] for d in by_fact[w.sessstore]["derived_from"]] == [w.cache]  # one hop only
    assert by_fact[w.other]["derived_from"] == []


def test_why_recalled_flat_nodes_and_edges(world, lin):
    w = world
    res = lin.why_recalled(w.recall1)
    ids = {n["id"] for n in res["nodes"]}
    assert w.recall1 in ids and all(e["from"] in ids and e["to"] in ids for e in res["edges"])
    returned = [e for e in res["edges"] if e["rel"] == "RETURNED"]
    assert len(returned) == len(w.results1)
    assert {(e["to"], e["props"]["rank"]) for e in returned} == {
        (r["fact_id"], i) for i, r in enumerate(w.results1, 1)
    }
    rels = {e["rel"] for e in res["edges"]}
    assert {"BY", "IN_STEP", "RETURNED", "ABOUT", "ASSERTED_BY", "DERIVED_FROM", "IN_SCOPE"} <= rels
    fact_node = next(n for n in res["nodes"] if n["id"] == w.db1)
    assert fact_node["label"] == "Fact" and fact_node["props"]["predicate"] == "database"
    assert len(res["nodes"]) + len(res["edges"]) <= 200


def test_why_recalled_single_result_and_empty(world, lin):
    w = world
    res = lin.why_recalled(w.recall2)
    assert [(r["rank"], r["fact_id"]) for r in res["results"]] == [(1, w.db1)]
    empty = lin.record_recall("planner", None, "nothing", w.proj, 3, [])
    res = lin.why_recalled(empty)
    assert res["results"] == [] and res["recall"]["step"] is None


def test_why_recalled_unknown_and_bounded(world, lin):
    w = world
    with pytest.raises(UnknownNode):
        lin.why_recalled("nope")
    res = lin.why_recalled(w.recall1, max_elements=22)
    assert len(res["nodes"]) + len(res["edges"]) <= 22
    assert res["truncated"] is True
    assert 0 < len(res["results"]) < len(w.results1)
    assert [r["rank"] for r in res["results"]] == list(range(1, len(res["results"]) + 1))  # best ranks kept


# -- who_knew -------------------------------------------------------------------------------------------
def test_who_knew_lists_exactly_the_agents_whose_steps_read_the_fact(world, lin):
    w = world
    res = lin.who_knew(w.db1)
    # researcher's step 3 READ it too: link_assert_result records the fact an assertion superseded as READ
    assert res["agents"] == ["builder", "planner", "researcher"]
    assert [(r["agent_id"], r["step_n"], r["at"]) for r in res["readers"]] == [
        ("planner", 1, 3000),
        ("builder", 1, 5000),
        ("researcher", 3, 6000),
    ]
    assert res["readers"][0]["recall_ids"] == [w.recall1]
    assert res["readers"][1]["recall_ids"] == [w.recall2]
    assert res["readers"][2]["recall_ids"] == []
    assert res["asserted_by"] == ["researcher"]  # the writer is listed separately, it did not READ it
    assert [(s["agent_id"], s["n"]) for s in res["written_by"]] == [("researcher", 1)]


def test_who_knew_other_facts(world, lin):
    w = world
    assert lin.who_knew(w.db2)["agents"] == ["builder"]  # only builder's step 2
    assert lin.who_knew(w.cache)["agents"] == ["planner"]
    nobody = lin.who_knew(w.db2)
    assert [(r["step_n"], r["at"]) for r in nobody["readers"]] == [(2, 7000)] and nobody["asserted_by"] == [
        "researcher"
    ]


def test_who_knew_fact_nobody_read_and_unknown(world, lin, eng):
    w = world
    unread = eng.assert_fact("Acme Notes API", "owner", "platform team", w.proj, "planner", now=8000)[
        "fact_id"
    ]
    res = lin.who_knew(unread)
    assert res["agents"] == [] and res["readers"] == [] and res["asserted_by"] == ["planner"]
    with pytest.raises(UnknownNode):
        lin.who_knew("ghost")


def test_who_knew_two_steps_same_agent(world, lin):
    w = world
    s = lin.record_step("builder", 3, at=8000)
    lin.record_recall("builder", s, "again", w.proj, 1, [{"fact_id": w.db2}], now=8000)
    res = lin.who_knew(w.db2)
    assert [(r["agent_id"], r["step_n"]) for r in res["readers"]] == [("builder", 2), ("builder", 3)]
    assert res["agents"] == ["builder"]


# -- knew_at --------------------------------------------------------------------------------------------
def test_knew_at_before_and_after_supersede_returns_v1_then_v2(world, lin):
    w = world
    before = lin.knew_at("builder", 1)
    assert [(f["fact_id"], f["value"]) for f in before["facts"]] == [(w.db1, "PostgreSQL 16")]
    assert (before["step_n"], before["at"]) == (1, 5000)
    after = lin.knew_at("builder", 2)
    # step 1 read v1, but v1 was superseded at 6000, so at step 2 (t=7000) only v2 is known
    assert [(f["fact_id"], f["value"]) for f in after["facts"]] == [(w.db2, "PostgreSQL 17")]
    assert (after["step_n"], after["at"]) == (2, 7000)
    assert after["facts"][0]["read_at_step"] == 2


def test_knew_at_planner_reads_and_writes(world, lin):
    w = world
    res = lin.knew_at("planner", 1)
    assert {f["fact_id"] for f in res["facts"]} == {r["fact_id"] for r in w.results1}
    assert [(x["id"], x["label"]) for x in res["wrote"]] == [(w.other, "Fact")]  # step 0 wrote 'language'
    later = lin.knew_at("planner", 2)
    assert {x["id"] for x in later["wrote"]} == {w.other, w.decision}
    assert next(x for x in later["wrote"] if x["id"] == w.decision)["label"] == "Decision"


def test_knew_at_researcher_only_wrote(world, lin):
    w = world
    res = lin.knew_at("researcher", 2)
    assert res["facts"] == []
    assert {x["id"] for x in res["wrote"]} == {w.db1, w.cache, w.sessstore}
    res3 = lin.knew_at("researcher", 3)
    assert w.db2 in {x["id"] for x in res3["wrote"]} and res3["step_n"] == 3


def test_knew_at_clamps_to_latest_step_and_handles_none(world, lin):
    w = world
    assert lin.knew_at("builder", 99)["step_n"] == 2
    none_yet = lin.knew_at("builder", 0)
    assert none_yet["step_n"] is None and none_yet["facts"] == [] and none_yet["wrote"] == []
    assert lin.knew_at("nobody", 5)["facts"] == []
    assert [f["fact_id"] for f in lin.knew_at("builder", 1)["facts"]] == [w.db1]


# -- as_of ----------------------------------------------------------------------------------------------
def test_as_of_at_three_times(world, lin):
    w = world
    assert lin.as_of("Acme Notes API", "database", 500, w.proj) is None  # before anything existed
    v1 = lin.as_of("acme  notes api", "Database", 5999, w.proj)  # names are normalised
    assert (v1["fact_id"], v1["value"], v1["status"]) == (w.db1, "PostgreSQL 16", "superseded")
    assert v1["valid_from"] == 1000 and v1["valid_to"] == 6000 and v1["asserted_by"] == ["researcher"]
    boundary = lin.as_of("Acme Notes API", "database", 6000, w.proj)
    assert (boundary["fact_id"], boundary["value"]) == (w.db2, "PostgreSQL 17")
    assert boundary["supersedes"] == [w.db1]
    now = lin.as_of("Acme Notes API", "database", 10**12, w.proj)
    assert now["fact_id"] == w.db2 and now["status"] == "active" and now["also_valid"] == []


def test_as_of_unknown_subject_predicate_or_scope(world, lin):
    w = world
    assert lin.as_of("Nobody", "database", 7000, w.proj) is None
    assert lin.as_of("Acme Notes API", "colour", 7000, w.proj) is None
    assert lin.as_of("Acme Notes API", "database", 7000, "no-scope") is None


def test_as_of_scope_inheritance_and_nearest_scope_wins(world, lin, eng):
    w = world
    eng.assert_fact("Acme Notes API", "region", "eu-west", w.glob, "planner", now=1500)
    assert lin.as_of("Acme Notes API", "region", 2000, w.proj)["scope_hops"] == 1  # inherited from global
    assert lin.as_of("Acme Notes API", "region", 2000, w.glob)["scope_hops"] == 0
    eng.assert_fact("Acme Notes API", "region", "us-east", w.proj, "planner", now=1800)
    best = lin.as_of("Acme Notes API", "region", 2000, w.proj)
    assert best["value"] == "us-east" and best["scope_hops"] == 0
    assert [a["value"] for a in [best]] == ["us-east"] and len(
        best["also_valid"]
    ) == 1  # global still valid too
    assert lin.as_of("Acme Notes API", "region", 1600, w.proj)["value"] == "eu-west"


def test_as_of_reports_contradictions_as_also_valid(world, lin, eng):
    w = world
    r = eng.assert_fact("Acme Notes API", "owner", "team a", w.proj, "planner", now=8000)
    r2 = eng.assert_fact("Acme Notes API", "owner", "team b", w.proj, "builder", now=8100)
    assert r2["contradicts"] == [r["fact_id"]]
    res = lin.as_of("Acme Notes API", "owner", 9000, w.proj)
    assert res["value"] == "team b" and [x["value"] for x in res["also_valid"]] == ["team a"]
    assert res["contradicts"] == [r["fact_id"]]


def test_as_of_agrees_with_engram_recall_as_of(world, lin, eng):
    w = world
    for t in (1500, 5500, 6500):
        recalled = {
            r["fact_id"] for r in eng.recall("database", w.proj, k=8, as_of=t) if r["predicate"] == "database"
        }
        assert recalled == {lin.as_of("Acme Notes API", "database", t, w.proj)["fact_id"]}


def test_valid_window_queries_do_not_write(world, client, graph, lin):
    before = cypher(client, graph, "MATCH (n) RETURN count(n)")
    lin.knew_at("builder", 2)
    lin.who_knew(world.db1)
    lin.as_of("Acme Notes API", "database", 5000, world.proj)
    assert cypher(client, graph, "MATCH (n) RETURN count(n)") == before
