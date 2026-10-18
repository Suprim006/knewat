"""C7X (P9-c): the labelled precision corpus. Corpus invariants, the gate's arithmetic, and a negative control."""

from __future__ import annotations

from collections import Counter, defaultdict

from plexus.crucible.config import quick_l1
from plexus.crucible.harness import Env
from plexus.crucible.l1 import C7X_PATH, c7x, load_c7x, rule_of_three

from .conftest import DB_HOST, DB_PORT

CATEGORIES = {
    "punctuation", "light", "heavy", "negation", "antonym", "quantifier", "number_word_same", "number_word_diff",
    "unit_same", "unit_diff", "direction_swap", "entity_swap", "near_numeric", "sprint_twin", "long_one_word",
    "bare_boolean",
}  # fmt: skip


def test_corpus_has_at_least_200_labelled_pairs_in_every_required_category():
    pairs = load_c7x()
    assert C7X_PATH.exists() and len(pairs) >= 200
    assert {p["category"] for p in pairs} == CATEGORIES
    assert len({p["id"] for p in pairs}) == len(pairs)
    assert len({p["subject"] for p in pairs}) == len(pairs)  # no pair can interact through entity resolution
    assert {p["expected"] for p in pairs} == {"merge", "distinct", "maybe"}
    assert all(
        p["split"] in ("train", "test") and p["a"].strip() and p["b"].strip() and p["a"] != p["b"]
        for p in pairs
    )
    assert (
        sum(1 for p in pairs if p["expected"] == "distinct") >= 100
    )  # rule of three: < 3% at 0 false merges


def test_split_is_balanced_inside_every_category_and_expected_is_constant_per_category():
    by: dict[str, list[dict]] = defaultdict(list)
    for p in load_c7x():
        by[p["category"]].append(p)
    for cat, ps in by.items():
        c = Counter(p["split"] for p in ps)
        assert abs(c["train"] - c["test"]) <= 1, (cat, c)
        assert len({p["expected"] for p in ps}) == 1, cat
        assert len(ps) >= 8, cat


def test_rule_of_three():
    assert rule_of_three(100) == 0.03
    assert rule_of_three(140) == 0.0214
    assert rule_of_three(0) is None


class _MergeEverything:
    """A deliberately wrong store: any second value for a subject+predicate is 'a duplicate' (no value is added)."""

    def __init__(self):
        self.seen: dict[tuple[str, str], str] = {}

    def register_agent(self, *_):
        return None

    def assert_fact(self, agent, subject, predicate, value, **_):
        self.seen.setdefault((subject, predicate), value)
        return {"fact_id": "x"}

    def facts(self, subject, predicate):
        v = self.seen.get((subject, predicate))
        return [] if v is None else [{"status": "active", "value": v}]


class _Run:
    def __init__(self, arm):
        self.arm = arm

    def open(self, _tag):
        return _MergeEverything()


def test_the_gate_catches_a_store_that_merges_everything_on_a_gated_arm():
    r = c7x(_Run("P"), 1, quick_l1())
    assert not r.passed and r.violations["false_merges"] == r.metrics["false_merges"] > 100
    assert r.violations["categories_with_false_merges"] > 5
    assert r.details["false_merge_upper_95"] is None  # no bound is claimed when there are false merges


def test_baseline_arms_are_measured_but_not_gated():
    r = c7x(_Run("B1"), 1, quick_l1())
    assert r.passed and r.metrics["false_merges"] > 100


def test_the_plexus_arm_has_zero_false_merges_on_a_slice(tmp_path, embedder_kind):
    env = Env(root=str(tmp_path / "root"), host=DB_HOST, port=DB_PORT, embedder=embedder_kind)
    pairs = [p for p in load_c7x() if p["category"] in ("negation", "unit_diff", "punctuation")][:30]
    from plexus.crucible.harness import ArmRun

    run = ArmRun(env, "P")
    try:
        r = c7x(run, 1, quick_l1(), pairs=pairs)
    finally:
        run.cleanup()
    assert r.passed, (r.violations, r.details)
    assert sum(c["pairs"] for c in r.details["by_category"].values()) == len(pairs)
