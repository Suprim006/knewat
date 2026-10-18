"""Slice 4a: the re-ranking function in isolation (no database)."""

from __future__ import annotations

import pytest

from knewat.activation import FactActivation, Settings
from knewat.activation.model import DAY_MS, Event, activation, neutral_activation
from knewat.activation.rank import rerank

NOW = 5_000 * DAY_MS
S = Settings(
    floor=0.5
)  # the mechanism tests use the original floor; the default (0.9) is pinned in test_settings


def fa(fact_id: str, *, age_days: float, used_days=(), surprise=0.0, protected=False) -> FactActivation:
    created = NOW - round(age_days * DAY_MS)
    events = [Event("create", created, 1.0)] + [Event("use", NOW - round(d * DAY_MS), 1.0) for d in used_days]
    return FactActivation(
        fact_id=fact_id,
        status="active",
        created_at=created,
        surprise=surprise,
        pinned=False,
        verify_state="verified",
        suspect_since=0,
        verify_after=9_999_999_999_999,
        events=events,
        activation=activation(events, now=NOW, created_at=created, surprise=surprise),
        protected=protected,
        protect_reasons=["decision:D"] if protected else [],
    )


def row(fact_id: str, distance: float, value: str = "v") -> dict:
    return {"fact_id": fact_id, "rank": distance, "score": distance, "value": value}


def order(rows, acts, k=10, **kw):
    return [r.row["fact_id"] for r in rerank(rows, acts, settings=S, k=k, **kw)]


def test_with_equal_relevance_the_recently_used_fact_ranks_first():
    rows = [row("old", 0.3), row("used", 0.3)]
    acts = {"old": fa("old", age_days=60), "used": fa("used", age_days=60, used_days=[0.01, 2])}
    assert order(rows, acts) == ["used", "old"]
    assert order(list(reversed(rows)), acts) == ["used", "old"], "input order must not matter"


def test_the_floor_keeps_a_relevant_unused_fact_above_an_irrelevant_used_one():
    rows = [row("relevant_old", 0.1), row("irrelevant_used", 0.6)]
    acts = {
        "relevant_old": fa("relevant_old", age_days=400),
        "irrelevant_used": fa("irrelevant_used", age_days=400, used_days=[0.001, 0.01, 0.1]),
    }
    got = rerank(rows, acts, settings=S, k=2)
    assert [r.row["fact_id"] for r in got] == ["relevant_old", "irrelevant_used"]
    assert got[0].multiplier == pytest.approx(0.5, abs=0.05), "decayed to the floor, not below it"
    assert got[1].multiplier > 0.98


def test_a_fact_the_activation_would_bury_still_gets_at_least_half_of_its_relevance():
    got = rerank([row("x", 0.2)], {"x": fa("x", age_days=3650)}, settings=S, k=1)[0]
    assert got.multiplier >= 0.5 and got.final >= 0.5 * got.relevance


def test_protected_facts_never_fall_below_neutral():
    acts = {"p": fa("p", age_days=90, protected=True), "u": fa("u", age_days=90)}
    got = {r.row["fact_id"]: r for r in rerank([row("p", 0.3), row("u", 0.3)], acts, settings=S, k=2)}
    assert got["p"].multiplier >= 0.75 - 1e-9
    assert got["u"].multiplier < 0.75
    assert got["p"].final > got["u"].final
    assert activation([Event("create", NOW - 90 * DAY_MS, 1.0)], now=NOW, created_at=0) < neutral_activation()


def test_a_surprising_fact_outranks_an_equal_plain_one():
    acts = {"plain": fa("plain", age_days=60), "contra": fa("contra", age_days=60, surprise=0.9)}
    assert order([row("plain", 0.3), row("contra", 0.3)], acts) == ["contra", "plain"]


def test_an_exact_keyword_hit_bypasses_the_penalty_but_a_partial_one_does_not():
    old = fa("old", age_days=400)
    rows = [row("kw", 0.3, "Redis cache ttl is 5 minutes"), row("part", 0.3, "Redis is fast")]
    got = {
        r.row["fact_id"]: r
        for r in rerank(
            rows,
            {"kw": old, "part": old},
            settings=S,
            k=2,
            kw_ids={"kw", "part"},
            words=["redis", "cache", "ttl"],
        )
    }
    assert got["kw"].multiplier == 1.0 and got["kw"].bypassed
    assert got["part"].multiplier < 0.6 and not got["part"].bypassed
    # a fact that merely contains the words but was not a full-text hit gets no bypass either
    nohit = rerank([rows[0]], {"kw": old}, settings=S, k=1, kw_ids=set(), words=["redis"])[0]
    assert not nohit.bypassed


def test_no_query_words_means_no_bypass():
    got = rerank([row("a", 0.3)], {"a": fa("a", age_days=400)}, settings=S, k=1, kw_ids={"a"}, words=[])
    assert not got[0].bypassed


def test_relevance_is_clamped_and_k_cuts_after_sorting():
    rows = [row("a", 1.7), row("b", -0.1), row("c", 0.5), row("d", 0.2)]
    acts = {i: fa(i, age_days=1) for i in "abcd"}
    got = rerank(rows, acts, settings=S, k=3)
    assert [r.row["fact_id"] for r in got] == ["b", "d", "c"]
    assert got[0].relevance == 1.0
    assert rerank([rows[0]], acts, settings=S, k=1)[0].relevance == 0.0


def test_ties_break_by_vector_rank_then_id():
    acts = {i: fa(i, age_days=5) for i in ("a", "b", "c")}
    rows = [row("c", 0.3), row("a", 0.3), row("b", 0.2)]
    assert order(rows, acts) == ["b", "a", "c"]


def test_a_missing_activation_is_treated_as_unused_not_as_an_error():
    got = rerank([row("ghost", 0.2)], {}, settings=S, k=1)
    assert got[0].multiplier == pytest.approx(0.5) and got[0].activation is None


def test_floor_and_a0_come_from_the_settings():
    acts = {"a": fa("a", age_days=3650)}
    low = rerank([row("a", 0.2)], acts, settings=Settings(floor=0.0), k=1)[0].multiplier
    assert low < 0.05
    hi = rerank([row("a", 0.2)], acts, settings=Settings(floor=0.9), k=1)[0].multiplier
    assert hi >= 0.9
    shifted = rerank([row("a", 0.2)], acts, settings=Settings(a0=-20.0), k=1)[0].multiplier
    assert shifted > 0.95, "with A0 far below the fact's activation it counts as strong"
