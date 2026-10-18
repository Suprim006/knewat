"""P12 fix 1: recall retrieval quality (scope 'all', candidate pool, keyword channel over entity + predicate,
score fusion, short tokens, logged keyword failures, the page signal) and the search_text backfill."""

from __future__ import annotations

import logging

import pytest
from redis.exceptions import ResponseError

from plexus.embed import HashEmbedder
from plexus.engram import migrate
from plexus.engram import service as svc
from plexus.engram.service import Engram


@pytest.fixture
def eng(client, graph):
    return Engram(client, graph, HashEmbedder())


@pytest.fixture
def glob(eng):
    return eng.create_scope("global", "global")


@pytest.fixture
def proj(eng, glob):
    return eng.create_scope("project", "billing", inherits=[glob])


# ------------------------------------------------------------------------------------------- pure parts
def test_query_words_keep_short_tokens_with_digits_and_two_letter_words():
    words = svc._query_words("v2 of p9 the db is S07 billing_cycle")
    assert words == ["v2", "p9", "the", "db", "s07", "billing", "cycle"]  # 'of', 'is' are dropped


def test_search_text_splits_the_predicate_into_words():
    assert svc.search_text("Bolt Billing API S07", "billing_cycle") == "Bolt Billing API S07 billing cycle"
    assert svc.search_text("Acme", "billing.cycle-x") == "Acme billing cycle x"


def _row(fid, ent, pred, val, dist):
    return {"fact_id": fid, "entity_name": ent, "predicate": pred, "value": val, "score": dist, "rank": dist}


def test_fuse_scores_weights_rare_words_over_common_ones():
    rows = [
        _row(f"s{n:02d}", f"Bolt Billing API S{n:02d}", "billing_cycle", f"day {n}", 0.66)
        for n in range(1, 21)
    ]
    rows.append(_row("acme7", "Acme Notes API S07", "api_version", "v14", 0.30))
    target = rows[6]  # S07, the same distance as its 19 siblings
    svc.fuse_scores(rows, svc._query_words("billing cycle decided in sprint S07"))
    best = max(rows, key=lambda r: r["fused"])
    assert best is target and target["lexical"] == pytest.approx(1.0)
    # weight 0 = the vector order of earlier versions: the nearest (Acme) fact wins
    svc.fuse_scores(rows, svc._query_words("billing cycle decided in sprint S07"), 0.0)
    assert max(rows, key=lambda r: r["fused"])["fact_id"] == "acme7"


def test_sibling_boost_only_for_the_best_seeds_and_never_from_zero_similarity():
    rows = [
        {**_row("a", "A", "p", "x", 0.2), "sib_of": ["b"]},
        {**_row("b", "A", "q", "y", 0.5), "sib_of": ["a"]},
        {**_row("c", "C", "p", "z", 0.4), "sib_of": ["d"]},
        {**_row("d", "C", "q", "w", 1.0), "sib_of": ["c"]},  # no similarity: never a seed
    ]
    svc._sibling_boost(rows, 1)  # one seed: 'a'
    by = {r["fact_id"]: r for r in rows}
    assert by["b"]["rank"] == pytest.approx(0.45) and by["b"]["via"] == "a"
    assert by["c"]["rank"] == pytest.approx(0.4) and by["c"]["via"] is None  # 'd' is no seed
    assert by["a"]["rank"] == pytest.approx(0.2) and by["a"]["via"] is None


def test_new_defaults():
    import inspect

    sig = inspect.signature(Engram.recall)
    assert sig.parameters["k"].default == svc.DEFAULT_K == 20
    assert sig.parameters["budget_chars"].default == svc.DEFAULT_BUDGET_CHARS == 6000


# ------------------------------------------------------------------------------------------- the store
def _sprints(eng, glob, proj):
    for n in range(1, 21):
        eng.assert_fact(
            f"Bolt Billing API S{n:02d}", "billing_cycle", f"monthly, invoiced on day {n}", proj, "p"
        )
        eng.assert_fact(f"Acme Notes API S{n:02d}", "api_version", f"v{2 * n}", glob, "r")


def test_scope_all_finds_project_facts_global_does_not(eng, glob, proj):
    _sprints(eng, glob, proj)
    q = "billing cycle of the Bolt Billing API decided in sprint S07"
    assert not any(r["entity"] == "Bolt Billing API S07" for r in eng.recall(q, glob))
    hits = eng.recall(q, glob, all_scopes=True)
    assert hits[0]["entity"] == "Bolt Billing API S07" and hits[0]["value"] == "monthly, invoiced on day 7"
    # a project scope sees its own facts and global's, as before
    assert eng.recall(q, proj)[0]["entity"] == "Bolt Billing API S07"


def test_keyword_channel_matches_entity_name_and_predicate(eng, client, graph, glob, proj):
    _sprints(eng, glob, proj)
    params = {
        "text": "bolt|s13",
        "scope_id": glob,
        "all": True,
        "k": 5,
        "t": svc._now_ms(),
        "statuses": ["active"],
    }
    ids = [r["id"] for r in client.ro(graph, "engram/recall_keywords", params)]
    got = (
        client.graph(graph)
        .ro_query(
            "UNWIND $ids AS i MATCH (f:Fact {id: i})-[:ABOUT]->(e:Entity) RETURN e.name, f.search_text",
            {"ids": ids},
        )
        .result_set
    )
    # neither value contains 'bolt' or 's13': both hits come from search_text (entity name + predicate words)
    assert ["Bolt Billing API S13", "Bolt Billing API S13 billing cycle"] in got
    assert ["Acme Notes API S13", "Acme Notes API S13 api version"] in got


def test_short_token_query_reaches_the_keyword_side(eng, glob):
    eng.assert_fact("Gateway", "protocol", "v2", glob, "a")
    eng.assert_fact("Gateway", "owner", "team blue", glob, "a")
    hits = eng.recall("v2", glob, k=1, forgetting=False)
    assert hits[0]["value"] == "v2"


def test_page_says_what_was_left_out(eng, glob):
    for i in range(6):
        eng.assert_fact(f"Svc{i}", "owner", f"team {i} owner of service {i}", glob, "a")
    rows, page = eng.recall_page("owner", glob, k=2)
    assert len(rows) == 2 and page["more_available"] and page["truncated"] and page["omitted_by_budget"] == 0
    rows, page = eng.recall_page("owner", glob, k=6, budget_chars=60)
    assert len(rows) < 6 and page["omitted_by_budget"] == 6 - len(rows) and page["truncated"]
    rows, page = eng.recall_page("owner", glob, k=50)
    assert len(rows) == 6 and not page["truncated"]


def test_keyword_failure_is_logged_not_swallowed(eng, glob, monkeypatch, caplog):
    eng.assert_fact("Acme", "owner", "alice", glob, "a")
    real = eng.client.ro

    def boom(graph, name, params=None, *a, **kw):
        if name == "engram/recall_keywords":
            raise ResponseError("Syntax error at offset 3")
        return real(graph, name, params, *a, **kw)

    monkeypatch.setattr(eng.client, "ro", boom)
    with caplog.at_level(logging.WARNING, logger="plexus.engram"):
        hits = eng.recall("Acme owner", glob)
    assert hits and hits[0]["value"] == "alice"  # the vector side still answers
    assert any("keyword channel failed" in r.getMessage() for r in caplog.records)


def test_migrate_backfills_search_text_on_old_facts(eng, client, graph, glob):
    eng.assert_fact("Bolt Billing API S07", "billing_cycle", "quarterly", glob, "a")
    client.graph(graph).query("MATCH (f:Fact) REMOVE f.search_text")  # a fact written before P12
    assert (
        svc.Engram(client, graph, HashEmbedder())._keyword_ids("bolt", glob, 5, svc._now_ms(), ["active"])
        == []
    )
    assert migrate.backfill_search_text(client, graph, dry_run=True) == {"missing": 1, "updated": 0}
    assert migrate.backfill_search_text(client, graph) == {"missing": 1, "updated": 1}
    assert migrate.backfill_search_text(client, graph) == {"missing": 0, "updated": 0}
    assert len(eng._keyword_ids("bolt", glob, 5, svc._now_ms(), ["active"])) == 1
