"""Pins for the P8-c refactor: the report renderer, the shared backend helpers and ``RunResult.conclude``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knewat.crucible.api import ClaimConflict, UnknownReference
from knewat.crucible.backends import base
from knewat.crucible.harness import RunResult
from knewat.crucible.report import render

RESULTS = Path(__file__).resolve().parents[2] / "src" / "knewat" / "crucible" / "results" / "20261014T204729Z"


def test_report_renders_byte_identical_to_the_committed_one():
    doc = json.loads((RESULTS / "results.json").read_text(encoding="utf-8"))
    committed = (RESULTS / "report.md").read_bytes().decode("utf-8")
    assert render(doc) == committed


def test_conclude_equals_the_manual_sequence():
    a = RunResult(seed=1)
    a.violations, a.metrics, a.details = {"x": 0}, {"n": 2}, {"d": 1}
    a.set_errors([ValueError("boom")])
    a.finish()
    b = RunResult(seed=1).conclude({"x": 0}, {"n": 2}, details={"d": 1}, errors=[ValueError("boom")])
    assert a.to_json() == b.to_json()
    assert a.error_total == b.error_total == 1
    assert not b.passed  # the error counts as a violation


def test_conclude_without_details_or_errors_keeps_the_defaults():
    r = RunResult(seed=1).conclude({"x": 0}, {})
    assert r.passed and r.details == {} and r.errors == [] and r.error_total == 0


def test_assert_result_shape():
    closing, clashing = [{"id": "a"}], [{"id": "b"}, {"id": "c"}]
    assert base.assert_result("f", None, closing, clashing) == {
        "fact_id": "f",
        "duplicate_of": None,
        "superseded": ["a"],
        "contradicts": ["b", "c"],
    }
    assert list(base.assert_result("f", "f", [], [])) == [
        "fact_id",
        "duplicate_of",
        "superseded",
        "contradicts",
    ]


def test_check_completable_reports_the_same_conflicts_as_the_backends():
    task = {"status": "claimed", "claimed_by": "w1", "version": 3}
    base.check_completable("t", "w1", 3, task)
    with pytest.raises(UnknownReference, match="unknown task id"):
        base.check_completable("t", "w1", 3, None)
    with pytest.raises(ClaimConflict, match="not claimed"):
        base.check_completable("t", "w1", 3, {**task, "status": "open"})
    with pytest.raises(ClaimConflict, match="claimed by w1, not w2"):
        base.check_completable("t", "w2", 3, task)
    with pytest.raises(ClaimConflict, match="stale version 2; current is 3"):
        base.check_completable("t", "w1", 2, task)


def test_argument_checks():
    with pytest.raises(ValueError, match="lease_ms"):
        base.check_lease(0)
    with pytest.raises(ValueError, match="uri"):
        base.check_source_uri("  ")
    assert base.decision_facts(["a", "b", "a"]) == ["a", "b"]
    with pytest.raises(ValueError, match="at most 100"):
        base.decision_facts([str(i) for i in range(101)])


def test_task_helpers():
    tasks = [{"id": "a", "depends_on": ["b", "x", "b"]}, {"title": "no id", "depends_on": None}]
    ids = base.new_task_ids(tasks, lambda: "minted")
    assert ids == ["a", "minted"]
    assert base.task_deps(tasks[0]) == ["b", "x"] and base.task_deps(tasks[1]) == []
    assert base.external_deps(tasks, ["a", "b"]) == ["x"]
    with pytest.raises(ValueError, match="duplicate task id"):
        base.new_task_ids([{"id": "a"}, {"id": "a"}], lambda: "m")
    with pytest.raises(UnknownReference, match="x, y"):
        base.raise_missing_deps(["x", "y"])
    base.raise_missing_deps([])


def test_artifact_specs_mint_ids_through_the_callers_function():
    arts = base.artifact_specs([{"uri": "u"}, {"id": "keep", "kind": "file", "hash": 5}], lambda: "m1")
    assert arts == [
        {"id": "m1", "kind": "", "uri": "u", "hash": "", "summary": ""},
        {"id": "keep", "kind": "file", "uri": "", "hash": "5", "summary": ""},
    ]
