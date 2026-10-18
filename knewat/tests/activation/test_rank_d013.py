"""D-013: re-ranking with pattern separation (no database)."""

from __future__ import annotations

import math

import pytest

from knewat.activation import FactActivation, Settings
from knewat.activation import score as S
from knewat.activation.model import DAY_MS, Event, activation
from knewat.activation.rank import lures_of, rerank

NOW = 5_000 * DAY_MS


def fa(fact_id: str, *, age_days: float, used_days=(), protected=False) -> FactActivation:
    created = NOW - round(age_days * DAY_MS)
    events = [Event("create", created, 1.0)] + [Event("use", NOW - round(d * DAY_MS), 1.0) for d in used_days]
    return FactActivation(
        fact_id=fact_id,
        status="active",
        created_at=created,
        surprise=0.0,
        pinned=False,
        verify_state="verified",
        suspect_since=0,
        verify_after=9_999_999_999_999,
        events=events,
        activation=activation(events, now=NOW, created_at=created),
        protected=protected,
        protect_reasons=["decision:D"] if protected else [],
    )


def row(fact_id: str, distance: float, entity: str = "e", predicate: str = "p", value: str = "v") -> dict:
    return {
        "fact_id": fact_id,
        "rank": distance,
        "score": distance,
        "entity_id": entity,
        "entity_name": f"Thing {entity}",
        "predicate": predicate,
        "value": value,
    }


def ids(ranked):
    return [r.row["fact_id"] for r in ranked]


MULT = Settings()  # the shipped default: separation on, cues entity + predicate
WE, WP = S.W_ENTITY_DEFAULT, S.W_PREDICATE_DEFAULT


# -- pattern separation -------------------------------------------------------------------------------


def test_a_fact_about_the_named_entity_beats_a_nearer_twin_about_another_entity():
    rows = [row("twin", 0.285, entity="s08"), row("target", 0.30, entity="s07")]
    acts = {"twin": fa("twin", age_days=30), "target": fa("target", age_days=30)}
    plain = rerank(rows, acts, settings=MULT, k=2, entities={}, forgetting=False)
    assert ids(plain) == ["twin", "target"]
    got = rerank(rows, acts, settings=MULT, k=2, entities={"s07": 10}, forgetting=False)
    assert ids(got) == ["target", "twin"]
    t, w = got
    assert t.ent_match and t.fan == 10 and t.sep == pytest.approx(WE * (5 - math.log(10)))
    assert not t.pred_match and t.pred_fan == 0
    assert not w.ent_match and w.sep == 0.0
    assert t.lures == ("twin",) and w.lures == ("target",), "same predicate, other entity, within 0.02"


def test_the_predicate_cue_separates_two_facts_about_the_same_named_entity():
    """CROSS_CHECK §3.2: the entity cue lifts every fact of the named entity equally; the predicate cue
    picks the one the query asks for, and the two cues add."""
    rows = [
        row("status", 0.285, entity="s07", predicate="status"),
        row("deadline", 0.30, entity="s07", predicate="deadline"),
        row("twin", 0.29, entity="s08", predicate="deadline"),
    ]
    ent_only = rerank(rows, {}, settings=MULT, k=3, entities={"s07": 12}, forgetting=False)
    assert ids(ent_only) == ["status", "deadline", "twin"], "the entity cue cannot break a same-entity tie"
    got = rerank(
        rows,
        {},
        settings=MULT,
        k=3,
        entities={"s07": 12},
        predicates={"deadline": 20},
        forgetting=False,
    )
    assert ids(got) == ["deadline", "status", "twin"]
    d, s, w = got
    assert d.ent_match and d.pred_match and d.fan == 12 and d.pred_fan == 20
    assert d.sep == pytest.approx(WE * (5 - math.log(12)) + WP * (5 - math.log(20)))
    assert s.ent_match and not s.pred_match and s.sep == pytest.approx(WE * (5 - math.log(12)))
    assert not w.ent_match and w.pred_match and w.sep == pytest.approx(WP * (5 - math.log(20)))


def test_a_hub_entity_gets_no_lift_and_the_lift_shrinks_with_the_fan():
    rows = [row("twin", 0.28, entity="s08"), row("target", 0.30, entity="hub")]
    acts = {}
    # a fan of 50 still lifts a little (S = 5 > ln 50), a fan of 200 (> e^5) lifts nothing
    got = rerank(rows, acts, settings=MULT, k=2, entities={"hub": 200}, forgetting=False)
    assert ids(got) == ["twin", "target"] and got[1].sep == 0.0 and got[1].ent_match
    fifty = rerank(rows, acts, settings=MULT, k=2, entities={"hub": 50}, forgetting=False)[0]
    assert fifty.row["fact_id"] == "target" and fifty.sep == pytest.approx(WE * (5 - math.log(50)))
    small = rerank(rows, acts, settings=MULT, k=2, entities={"hub": 2}, forgetting=False)[0]
    mid = rerank(rows, acts, settings=MULT, k=2, entities={"hub": 20}, forgetting=False)[0]
    assert small.row["fact_id"] == "target" and small.sep > mid.sep > fifty.sep > 0


def test_separation_off_ignores_the_entities_and_reports_no_lures():
    rows = [row("twin", 0.28, entity="s08"), row("target", 0.30, entity="s07")]
    got = rerank(rows, {}, settings=MULT, k=2, entities={"s07": 1}, forgetting=False, separation=False)
    assert ids(got) == ["twin", "target"] and all(r.sep == 0.0 and r.lures == () for r in got)
    off = Settings(separation=False)
    got = rerank(rows, {}, settings=off, k=2, entities={"s07": 1}, forgetting=False)
    assert ids(got) == ["twin", "target"]


def test_both_switches_off_is_the_plain_relevance_order_with_multiplier_one():
    rows = [row("c", 0.30), row("a", 0.30), row("b", 0.20)]
    acts = {"a": fa("a", age_days=1, used_days=[0.1]), "b": fa("b", age_days=900), "c": fa("c", age_days=900)}
    got = rerank(rows, acts, settings=MULT, k=3, forgetting=False, separation=False)
    assert ids(got) == ["b", "a", "c"]
    assert all(r.multiplier == 1.0 and r.final == pytest.approx(r.relevance) for r in got)


def test_lures_need_the_same_predicate_another_entity_and_a_small_relevance_gap():
    rows = [
        row("a", 0.30, entity="e1", predicate="p"),
        row("b", 0.31, entity="e2", predicate="p"),
        row("c", 0.30, entity="e1", predicate="p"),  # same entity: not a lure of a
        row("d", 0.30, entity="e3", predicate="q"),  # other predicate
        row("e", 0.36, entity="e4", predicate="p"),  # too far
    ]
    rels = [1 - r["rank"] for r in rows]
    assert lures_of(rows, rels)[0] == ("b",)
    assert lures_of(rows, rels)[1] == ("a", "c")


# -- keyword bypass over the fact text ---------------------------------------------------------------------


def test_the_bypass_tests_the_whole_fact_text():
    r = row("f", 0.30, entity="s07", predicate="api_version", value="v14")
    r["entity_name"] = "Acme Notes API S07"
    acts = {"f": fa("f", age_days=400)}
    words = ["acme", "notes", "api", "s07", "version"]  # the tokeniser splits api_version
    got = rerank([r], acts, settings=MULT, k=1, kw_ids={"f"}, words=words, forgetting=True, separation=False)[
        0
    ]
    assert got.bypassed and got.multiplier == 1.0


# -- multiplier and ordering ----------------------------------------------------------------------------


def test_a_protected_fact_is_lifted_to_neutral():
    rows = [row("p", 0.30), row("u", 0.30)]
    acts = {"p": fa("p", age_days=90, protected=True), "u": fa("u", age_days=90)}
    got = {
        r.row["fact_id"]: r for r in rerank(rows, acts, settings=Settings(floor=0.5), k=2, separation=False)
    }
    assert got["p"].multiplier >= 0.75 - 1e-9 > got["u"].multiplier


def test_a_zero_relevance_row_sorts_last_and_k_cuts_after_sorting():
    rows = [row("a", 1.7), row("b", -0.1), row("c", 0.5), row("d", 0.2)]
    acts = {i: fa(i, age_days=1) for i in "abcd"}
    got = rerank(rows, acts, settings=MULT, k=4, separation=False)
    assert ids(got) == ["b", "d", "c", "a"] and got[-1].final == 0.0
    assert ids(rerank(rows, acts, settings=MULT, k=2, separation=False)) == ["b", "d"]
