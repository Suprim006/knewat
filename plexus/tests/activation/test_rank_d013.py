"""D-013: re-ranking with pattern separation, the additive mode and the band guard (no database)."""

from __future__ import annotations

import math

import pytest

from plexus.activation import FactActivation, Settings
from plexus.activation import score as S
from plexus.activation.model import DAY_MS, Event, activation, activation_spaced, neutral_activation
from plexus.activation.rank import lures_of, rerank

NOW = 5_000 * DAY_MS
A = 0.177


def fa(
    fact_id: str, *, age_days: float, used_days=(), protected=False, salience=0.0, add=False
) -> FactActivation:
    created = NOW - round(age_days * DAY_MS)
    events = [Event("create", created, 1.0)] + [Event("use", NOW - round(d * DAY_MS), 1.0) for d in used_days]
    act = (
        activation_spaced(events, now=NOW, created_at=created, a0=neutral_activation(A))[0]
        if add
        else activation(events, now=NOW, created_at=created)
    )
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
        activation=act,
        protected=protected,
        protect_reasons=["decision:D"] if protected else [],
        salience=salience,
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


MULT = Settings()  # mult, separation on, kw bypass over the fact text, cues entity+predicate
ADD = Settings(act_mode="add")
MULT1 = Settings(cues="entity")  # the single damped entity cue P1 first shipped
WE, WP = S.W_ENTITY_DEFAULT, S.W_PREDICATE_DEFAULT


# -- pattern separation -------------------------------------------------------------------------------


def test_a_fact_about_the_named_entity_beats_a_nearer_twin_about_another_entity():
    rows = [row("twin", 0.285, entity="s08"), row("target", 0.30, entity="s07")]
    acts = {"twin": fa("twin", age_days=30), "target": fa("target", age_days=30)}
    for settings in (MULT, ADD):
        plain = rerank(rows, acts, settings=settings, k=2, entities={}, forgetting=False)
        assert ids(plain) == ["twin", "target"]
        got = rerank(rows, acts, settings=settings, k=2, entities={"s07": 10}, forgetting=False)
        assert ids(got) == ["target", "twin"]
        t, w = got
        assert t.ent_match and t.fan == 10 and t.sep == pytest.approx(WE * (5 - math.log(10)))
        assert not t.pred_match and t.pred_fan == 0
        assert not w.ent_match and w.sep == 0.0
        assert t.lures == ("twin",) and w.lures == ("target",), "same predicate, other entity, within 0.02"
    one = rerank(rows, acts, settings=MULT1, k=2, entities={"s07": 10}, forgetting=False)
    assert ids(one) == ["target", "twin"]
    assert one[0].sep == pytest.approx(0.15 * (1 - math.log(10) / math.log(50))), "cues=entity: the P1 form"


def test_the_predicate_cue_separates_two_facts_about_the_same_named_entity():
    """CROSS_CHECK §3.2: the entity cue lifts every fact of the named entity equally; the predicate cue
    picks the one the query asks for, and the two cues add."""
    rows = [
        row("status", 0.285, entity="s07", predicate="status"),
        row("deadline", 0.30, entity="s07", predicate="deadline"),
        row("twin", 0.29, entity="s08", predicate="deadline"),
    ]
    for settings in (MULT, ADD):
        ent_only = rerank(rows, {}, settings=settings, k=3, entities={"s07": 12}, forgetting=False)
        assert ids(ent_only) == ["status", "deadline", "twin"], (
            "the entity cue cannot break a same-entity tie"
        )
        got = rerank(
            rows,
            {},
            settings=settings,
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
    # the single-cue form ignores the predicate
    one = rerank(
        rows, {}, settings=MULT1, k=3, entities={"s07": 12}, predicates={"deadline": 20}, forgetting=False
    )
    assert ids(one) == ["status", "deadline", "twin"] and not one[0].pred_match


def test_a_hub_entity_gets_no_lift_and_the_lift_shrinks_with_the_fan():
    rows = [row("twin", 0.28, entity="s08"), row("target", 0.30, entity="hub")]
    acts = {}
    # two cues: a fan of 50 still lifts a little (S = 5 > ln 50), a fan of 200 (> e^5) lifts nothing
    got = rerank(rows, acts, settings=MULT, k=2, entities={"hub": 200}, forgetting=False)
    assert ids(got) == ["twin", "target"] and got[1].sep == 0.0 and got[1].ent_match
    fifty = rerank(rows, acts, settings=MULT, k=2, entities={"hub": 50}, forgetting=False)[0]
    assert fifty.row["fact_id"] == "target" and fifty.sep == pytest.approx(WE * (5 - math.log(50)))
    small = rerank(rows, acts, settings=MULT, k=2, entities={"hub": 2}, forgetting=False)[0]
    mid = rerank(rows, acts, settings=MULT, k=2, entities={"hub": 20}, forgetting=False)[0]
    assert small.row["fact_id"] == "target" and small.sep > mid.sep > fifty.sep > 0
    # the single-cue form: zero at fan 50
    got = rerank(rows, acts, settings=MULT1, k=2, entities={"hub": 50}, forgetting=False)
    assert ids(got) == ["twin", "target"] and got[1].sep == 0.0 and got[1].ent_match
    small = rerank(rows, acts, settings=MULT1, k=2, entities={"hub": 2}, forgetting=False)[0]
    mid = rerank(rows, acts, settings=MULT1, k=2, entities={"hub": 20}, forgetting=False)[0]
    assert small.row["fact_id"] == "target" and small.sep > mid.sep > 0


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
    for settings in (MULT, ADD):
        got = rerank(rows, acts, settings=settings, k=3, forgetting=False, separation=False)
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


def test_the_bypass_tests_the_whole_fact_text_by_default_and_the_value_alone_in_legacy_mode():
    r = row("f", 0.30, entity="s07", predicate="api_version", value="v14")
    r["entity_name"] = "Acme Notes API S07"
    acts = {"f": fa("f", age_days=400)}
    words = ["acme", "notes", "api", "s07", "version"]  # the tokeniser splits api_version
    got = rerank([r], acts, settings=MULT, k=1, kw_ids={"f"}, words=words, forgetting=True, separation=False)[
        0
    ]
    assert got.bypassed and got.multiplier == 1.0
    legacy = Settings(kw_bypass="value")
    got = rerank(
        [r], acts, settings=legacy, k=1, kw_ids={"f"}, words=words, forgetting=True, separation=False
    )[0]
    assert not got.bypassed and got.multiplier < 1.0


# -- additive mode -------------------------------------------------------------------------------------


def test_add_mode_activation_only_moves_a_score_by_less_than_beta():
    rows = [row("hot", 0.30), row("cold", 0.30)]
    acts = {
        "hot": fa("hot", age_days=90, used_days=[d for d in range(1, 90)], add=True),
        "cold": fa("cold", age_days=90, add=True),
    }
    got = {r.row["fact_id"]: r for r in rerank(rows, acts, settings=ADD, k=2, separation=False)}
    assert got["hot"].final > got["cold"].final
    assert abs(got["hot"].act) < 0.05 and abs(got["cold"].act) < 0.05
    assert got["hot"].score == pytest.approx(math.log(0.7) + got["hot"].act)
    # a 12% relevance gap can never be overturned by activation alone
    rows = [row("hot", 0.40), row("cold", 0.30)]
    assert ids(rerank(rows, acts, settings=ADD, k=2, separation=False)) == ["cold", "hot"]


def test_add_mode_a_protected_fact_is_not_lifted_to_neutral_but_the_band_guard_applies():
    # a protected (critical) twin outside the relevance band, a plain target inside it
    rows = [row("target", 0.30), row("critical", 0.35)]
    acts = {
        "target": fa("target", age_days=90, add=True),
        "critical": fa("critical", age_days=90, used_days=[90], protected=True, salience=0.86, add=True),
    }
    got = {r.row["fact_id"]: r for r in rerank(rows, acts, settings=ADD, k=2, separation=False)}
    assert got["target"].in_band and not got["critical"].in_band
    assert got["critical"].sal == 0.0, "the band holds nothing critical: the tail is not suppressed"
    assert got["critical"].act <= 0.0, "no max(A, A0) lift in add mode"
    # when the band itself holds something critical, the tail is suppressed by delta * s_max_band
    rows = [row("crit_in", 0.30), row("plain_out", 0.35)]
    acts = {
        "crit_in": fa("crit_in", age_days=90, protected=True, salience=0.9, add=True),
        "plain_out": fa("plain_out", age_days=90, add=True),
    }
    got = {r.row["fact_id"]: r for r in rerank(rows, acts, settings=ADD, k=2, separation=False)}
    assert got["crit_in"].sal == pytest.approx(0.03 * 0.9)
    assert got["plain_out"].sal == pytest.approx(-0.03 * 0.9)


def test_mult_mode_still_lifts_a_protected_fact_to_neutral():
    rows = [row("p", 0.30), row("u", 0.30)]
    acts = {"p": fa("p", age_days=90, protected=True), "u": fa("u", age_days=90)}
    got = {
        r.row["fact_id"]: r for r in rerank(rows, acts, settings=Settings(floor=0.5), k=2, separation=False)
    }
    assert got["p"].multiplier >= 0.75 - 1e-9 > got["u"].multiplier


def test_add_mode_score_is_score_dot_score_on_the_production_path(monkeypatch):
    """BRANCH_REVIEW finding 2: one formula. ``rerank``'s add branch must go through ``score.score``."""
    calls: list[dict] = []
    real = S.score

    def spy(rel, **kw):
        calls.append({"rel": rel, **kw})
        return real(rel, **kw)

    monkeypatch.setattr(S, "score", spy)
    rows = [
        row("named", 0.30, entity="e1", predicate="p"),
        row("twin", 0.28, entity="e2"),
        row("kw", 0.33, value="k"),
    ]
    acts = {
        "named": fa("named", age_days=90, used_days=[5, 40], add=True, salience=0.6),
        "twin": fa("twin", age_days=90, add=True),
        "kw": fa("kw", age_days=10, add=True),
    }
    st = Settings(act_mode="add")
    got = {
        r.row["fact_id"]: r
        for r in rerank(
            rows, acts, settings=st, k=3, kw_ids={"kw"}, words=["k"], entities={"e1": 3}, predicates={"p": 7}
        )
    }
    assert len(calls) == 3, "score() is called once per row in add mode"
    for r in got.values():
        kw = {
            "A": r.activation, "A0": st.neutral, "s_noise": st.s_noise, "beta": st.beta,
            "ent_match": r.ent_match, "fan": r.fan, "S_max": st.s_max, "gamma": st.gamma,
            "salience": r.salience, "in_band": r.in_band,
            "s_max_band": max(x.salience for x in got.values() if x.in_band),
            "delta": st.delta, "bypass": r.bypassed, "pred_match": r.pred_match, "pred_fan": r.pred_fan,
            "cues": st.cues, "w_entity": st.w_entity, "w_predicate": st.w_predicate, "S": st.cue_s,
        }  # fmt: skip
        assert r.score == pytest.approx(real(r.relevance, **kw))
        assert r.score == pytest.approx(math.log(r.relevance) + r.act + r.sep + r.sal)
        assert r.final == pytest.approx(math.exp(r.score))
        assert r.multiplier == pytest.approx(math.exp(r.act + r.sal))
    assert got["kw"].bypassed and got["kw"].act == 0.0 and got["kw"].sal == 0.0
    assert got["named"].sep > 0 and got["named"].act > 0 and got["named"].sal > 0
    # mult mode never goes through score()
    calls.clear()
    rerank(rows, acts, settings=Settings(), k=3, entities={"e1": 3})
    assert calls == []


def test_add_mode_a_zero_relevance_row_sorts_last_and_k_cuts_after_sorting():
    rows = [row("a", 1.7), row("b", -0.1), row("c", 0.5), row("d", 0.2)]
    acts = {i: fa(i, age_days=1, add=True) for i in "abcd"}
    got = rerank(rows, acts, settings=ADD, k=4, separation=False)
    assert ids(got) == ["b", "d", "c", "a"] and got[-1].score == float("-inf") and got[-1].final == 0.0
    assert ids(rerank(rows, acts, settings=ADD, k=2, separation=False)) == ["b", "d"]
