"""The committed combined results file (L1 + L4 + ablation + L2) that the View's Results page reads.

``latest.json`` is what ``crucible all`` writes (and overwrites on every run); ``latest-all.json`` is that file with
the full L2 run merged in (``python -m plexus.crucible.l2.run merge --into latest.json --l2
demo_data/crucible/l2/latest-full.json --write latest-all.json``). plexus-view carries a byte-identical copy as the
fixture of its Results test, so a drift between the two shows up here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "plexus" / "src" / "plexus" / "crucible" / "results"
ALL = RESULTS / "latest-all.json"
VIEW_COPY = ROOT / "plexus-view" / "src" / "fixtures" / "results.real.json"


@pytest.fixture(scope="module")
def doc() -> dict:
    return json.loads(ALL.read_text(encoding="utf-8"))


def test_envelope_and_layers(doc):
    assert doc["schema_version"] == 1 and doc["kind"] == "crucible-results"
    assert doc["run"]["layers"] == ["L1", "L4", "ablation", "L2"]
    assert set(doc["layers"]) == {"L1", "L4", "ablation", "L2"}


def test_l2_keys_the_view_reads(doc):
    l2 = doc["layers"]["L2"]
    assert l2["mode"] == "full" and l2["question_set"]["asked"] == l2["question_set"]["total"] == 43
    for arm in ("B0", "B1", "B2", "P"):
        a = l2["arms"][arm]
        assert a["accuracy"]["total"] == 43
        assert "accuracy_whole_reply_json" in a and "usage" in a and "by_family" in a
        for k in ("tokens_per_question", "cost_usd", "cost_per_question_usd", "latency_ms"):
            assert k in a["usage"]
    assert l2["arms"]["P"]["usage"]["cost_usd"] == 0
    assert any("methodology fix" in n for n in l2["notes"])


def test_l4_keys_the_view_reads(doc):
    l4 = doc["layers"]["L4"]
    assert l4["notes"] and l4["embedder_probe"]
    assert {p["arm"] for p in l4["claim_sweep"]} >= {"B1", "P"}
    # the tenant sweep carries `workers` too; the View must key it on `tenants`
    assert all("tenants" in p and "workers" in p for p in l4["tenant_sweep"])


def test_honesty_notes_replace_the_out_of_scope_l2_line(doc):
    assert not any(h.startswith("L2 (provenance questions answered by an LLM") for h in doc["honesty"])
    assert any("Plexus TIES them on accuracy" in h for h in doc["honesty"])


def test_view_fixture_is_a_copy_of_the_committed_file():
    assert VIEW_COPY.read_bytes() == ALL.read_bytes(), (
        "plexus-view/src/fixtures/results.real.json drifted from crucible/results/latest-all.json: cp it again"
    )
