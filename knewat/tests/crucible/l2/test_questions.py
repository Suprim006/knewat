"""Question generation (derived from the ledger), normalisation and strict reply parsing. No LLM, no database."""

from __future__ import annotations

from pathlib import Path

import pytest

from knewat.crucible.l2.questions import (
    FAMILIES,
    Question,
    build_questions,
    dump_questions,
    generate,
    load_questions,
    normalise,
    parse_reply,
    score,
)

ROOT = Path(__file__).resolve().parents[3]
COMMITTED = ROOT / "demo_data/crucible/questions.yaml"


@pytest.fixture(scope="module")
def truth(tmp_path_factory):
    return generate(tmp_path_factory.mktemp("l2truth"))


def test_about_forty_questions_in_every_family(truth):
    _, qs = truth
    assert 38 <= len(qs) <= 46
    assert len({q.id for q in qs}) == len(qs)
    by_family = {f: sum(q.family == f for q in qs) for f in FAMILIES}
    assert all(n >= 2 for n in by_family.values()), by_family
    assert all(q.kind in ("set", "ordered", "value", "yesno", "int") for q in qs)


def test_the_query_spec_stays_out_of_what_llm_arms_see(truth):
    _, qs = truth
    for q in qs:
        assert q.op and q.op not in q.prompt()


def test_ground_truth_is_stable(truth, tmp_path):
    led, qs = truth
    _, qs2 = generate(tmp_path)
    assert [q.to_json() for q in qs] == [q.to_json() for q in qs2]
    assert [q.to_json() for q in build_questions(led)] == [q.to_json() for q in qs]


def test_committed_file_matches_the_generator(truth):
    _, qs = truth
    assert COMMITTED.exists(), "run: python -m knewat.crucible.l2.run questions"
    assert [q.to_json() for q in load_questions(COMMITTED)] == [q.to_json() for q in qs]


def test_yaml_round_trip(truth, tmp_path):
    led, qs = truth
    p = tmp_path / "q.yaml"
    dump_questions(qs, led, p)
    assert [q.to_json() for q in load_questions(p)] == [q.to_json() for q in qs]


def mk(kind, item, answer):
    return Question("Q00", "handoffs", "t", "f", kind, item, answer, "op")


def test_set_scoring_is_order_and_case_insensitive():
    x = mk("set", "fact", ["api_version=v2", "auth_method=JWT bearer tokens (RS256)"])
    assert score(x, ["auth_method=jwt bearer tokens (rs256)", "api_version = v2"])[0]
    assert not score(x, ["api_version=v2"])[0]
    assert not score(x, ["api_version=v2", "auth_method=JWT bearer tokens (RS256)", "purpose=x"])[0]
    assert score(mk("set", "fact", []), [])[0]


def test_ordered_scoring_is_order_sensitive():
    x = mk("ordered", "value", ["v1", "v2"])
    assert score(x, ["v1", "v2"])[0] and not score(x, ["v2", "v1"])[0]


def test_decision_items_match_on_the_first_four_words():
    x = mk("set", "decision", ["use jwt bearer tokens"])
    assert score(x, ["Use JWT bearer tokens for user traffic (security requirement); offer API keys later."])[
        0
    ]


def test_fact_by_scoring():
    x = mk("set", "fact_by", ["api_version=v2@researcher"])
    assert score(x, ["api_version=v2 @ Researcher"])[0]
    assert not score(x, ["api_version=v2@planner"])[0]


def test_yesno_and_int():
    yn = mk("yesno", "value", "no")
    assert score(yn, "No")[0] and not score(yn, "maybe")[0]
    n = mk("int", "value", 2)
    assert score(n, 2)[0] and score(n, "2")[0]
    assert not score(n, True)[0] and not score(n, "two")[0]


def test_wrong_shapes_are_wrong_not_errors():
    assert score(mk("set", "task", ["a"]), "a") == (False, "unparseable answer: a list was expected")
    assert not score(mk("value", "agent", "builder"), ["builder"])[0]
    with pytest.raises(ValueError):
        normalise(mk("int", "value", 2), None)


@pytest.mark.parametrize(
    "text,final_ok,whole_ok",
    [
        ('{"answer": ["a"]}', True, True),
        ('```json\n{"answer": "x"}\n```', True, True),
        ('Reasoning first.\n\n{"answer": "x"}', True, False),
        ('Reasoning.\n```json\n{"answer": 2}\n```', True, False),
        ('Draft {"answer": "no"} then final {"answer": "yes"}', True, False),
        ('{"answer": "x"} and then some more text', False, False),
        ('{"answer": "x", "why": "y"}', False, False),
        ("[1]", False, False),
        ("", False, False),
        ("Sure, the answer is x", False, False),
    ],
)
def test_parse_reply_rules(text, final_ok, whole_ok):
    assert (parse_reply(text)[1] == "") is final_ok
    assert (parse_reply(text, strict=True)[1] == "") is whole_ok


def test_the_last_answer_object_wins():
    assert parse_reply('Draft {"answer": "no"} then final {"answer": "yes"}')[0] == "yes"
