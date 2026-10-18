"""End-to-end L2 run with the mocked CLI: results.json shape, scoring, caching, merge into H's schema."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from knewat.crucible.l2.questions import generate
from knewat.crucible.l2.run import PILOT_IDS, merge_into, render_report, run_l2

FAKE = [sys.executable, str(Path(__file__).with_name("fake_claude_l2.py"))]
COMMITTED = Path(__file__).resolve().parents[3] / "demo_data/crucible/questions.yaml"
DB_PORT = int(os.environ.get("KNEWAT_TEST_DB_PORT", "6310"))


@pytest.fixture
def fake_answers(tmp_path, monkeypatch):
    _, qs = generate(tmp_path / "t")
    ans = tmp_path / "answers.json"
    # the fake model gets every question right except Q15 (a time-travel set question)
    ans.write_text(json.dumps({q.id: (["v0"] if q.id == "Q15" else q.answer) for q in qs}), encoding="utf-8")
    monkeypatch.setenv("FAKE_ANSWERS", str(ans))
    monkeypatch.setenv("FAKE_COUNT", str(tmp_path / "count.txt"))
    return tmp_path / "count.txt"


def go(tmp_path, arms, **kw):
    return run_l2(
        mode="pilot", arms=arms, model="sonnet", budget_usd=5.0, host="127.0.0.1", port=DB_PORT,
        embedder="hash", out_root=tmp_path / "out", cache_dir=tmp_path / "cache", log=lambda s: None,
        launcher=FAKE, qpath=COMMITTED, run_id="t-pilot", **kw,
    )  # fmt: skip


def test_baselines_end_to_end_without_a_database(tmp_path, fake_answers):
    doc, d = go(tmp_path, ("B0", "B1", "B2"))
    layer = doc["layers"]["L2"]
    assert doc["schema_version"] == 1 and doc["kind"] == "crucible-results" and doc["run"]["layers"] == ["L2"]
    assert layer["question_set"]["ids"] == list(PILOT_IDS) and layer["question_set"]["total"] == 43
    for arm in ("B0", "B1", "B2"):
        a = layer["arms"][arm]
        assert a["accuracy"] == {"correct": 4, "total": 5, "pct": 80.0}
        assert [r["id"] for r in a["questions"]] == list(PILOT_IDS)
        bad = [r for r in a["questions"] if not r["correct"]]
        assert [r["id"] for r in bad] == ["Q15"] and bad[0]["got"] == ["v0"]
        assert (
            a["usage"]["llm_calls"] == 5 and a["usage"]["cost_usd"] == 0.05 and a["usage"]["total_tokens"] > 0
        )
        assert set(a["by_family"]) == {
            "decision_provenance",
            "time_travel",
            "supersession",
            "recovery",
            "forgetting",
        }
        assert a["context"]["questions_truncated"] == 0
    assert layer["arms"]["B2"]["context"]["chars_median"] < layer["arms"]["B0"]["context"]["chars_median"]
    assert layer["arms"]["B0"]["questions"][0]["context_chars"] <= layer["context_budget_chars"]
    assert (d / "results.json").exists() and (d / "report.md").exists() and (d / "B0.context.txt").exists()
    assert json.loads((d / "results.json").read_text(encoding="utf-8")) == doc
    assert "Q15" in render_report(doc)
    n = len((fake_answers).read_text().splitlines())
    assert n == 15
    go(tmp_path, ("B0", "B1", "B2"))  # second run: everything comes from the cache
    assert len(fake_answers.read_text().splitlines()) == n


def test_budget_cap_marks_the_arm_incomplete(tmp_path, fake_answers):
    doc, _ = run_l2(
        mode="pilot", arms=("B0",), model="sonnet", budget_usd=0.025, host="127.0.0.1", port=DB_PORT,
        embedder="hash", out_root=tmp_path / "out", cache_dir=tmp_path / "cache", log=lambda s: None,
        launcher=FAKE, qpath=COMMITTED, run_id="t-cap",
    )  # fmt: skip
    a = doc["layers"]["L2"]["arms"]["B0"]
    assert a["completed"] is False and a["accuracy"]["total"] == 3
    assert any("budget cap" in n for n in doc["layers"]["L2"]["notes"])


@pytest.mark.integration
def test_all_four_arms_and_merge(tmp_path, fake_answers):
    doc, _ = go(tmp_path, ("B0", "B1", "B2", "P"))
    p = doc["layers"]["L2"]["arms"]["P"]
    assert p["accuracy"] == {"correct": 5, "total": 5, "pct": 100.0}
    assert p["usage"]["cost_usd"] == 0 and p["usage"]["llm_calls"] == 0 and p["usage"]["statements"] >= 5
    assert all(r["tokens"] == 0 and r["statements"] >= 1 for r in p["questions"])
    assert doc["summary"]["l2_accuracy_pct"] == {"B0": 80.0, "B1": 80.0, "B2": 80.0, "P": 100.0}
    assert any("Knewat beats B0" in h for h in doc["summary"]["headline"])
    # merge into an H-shaped results.json
    base = {
        "schema_version": 1, "kind": "crucible-results", "run": {"id": "h", "layers": ["L1"]},
        "config": {"arms": ["B0", "P"]}, "arms": {"B0": {"label": "Files"}}, "layers": {"L1": {"title": "x"}},
        "summary": {"headline": ["L1 line"]}, "honesty": ["keep me"],
    }  # fmt: skip
    merged = merge_into(base, doc)
    assert set(merged["layers"]) == {"L1", "L2"} and merged["run"]["layers"] == ["L1", "L2"]
    assert merged["arms"]["B0"] == {"label": "Files"} and "B2" in merged["arms"]
    assert merged["summary"]["headline"][0] == "L1 line" and len(merged["summary"]["headline"]) > 1
    assert "keep me" in merged["honesty"] and merged["config"]["arms"] == ["B0", "P", "B1", "B2"]
    assert base["layers"] == {"L1": {"title": "x"}}  # the input is not mutated
