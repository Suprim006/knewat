"""The committed combined results file (L1 + L4 + ablation + L2 + L2-scale + B1h + C7x + L6) that the View's Results page reads.

``latest.json`` is what ``crucible all`` writes (and overwrites on every run); ``latest-all.json`` is that file with
the L2, L2-scale, B1h, C7-extended and L6 results merged in: ``python -m plexus.crucible.combine`` (``--check`` verifies it). The
test below proves the committed file is exactly that merge. plexus-view carries a byte-identical copy as the
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
    assert doc["run"]["layers"] == ["L1", "L4", "ablation", "L2", "L2_scale", "B1h", "C7x", "L6"]
    assert set(doc["layers"]) == {"L1", "L4", "ablation", "L2", "L2_scale", "B1h", "C7x", "L6"}


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


def test_l2_scale_keys_the_view_reads(doc):
    sc = doc["layers"]["L2_scale"]
    assert sc["question_set"]["asked"] == 36 and sc["question_set"]["total"] == 40
    got = {a: (v["accuracy"]["correct"], v["accuracy"]["wilson95_pct"]) for a, v in sc["arms"].items()}
    assert {a: c for a, (c, _) in got.items()} == {"P": 36, "B1": 32, "B0": 30, "B2": 23}
    assert got["P"][1] == [90.4, 100.0]
    for arm, v in sc["arms"].items():
        assert set(v["by_stratum"]) == {"early", "middle", "late"}
        assert all({"id", "correct"} <= set(q) for q in v["questions"])
        assert ("failure_analysis" in v) == (arm != "P")
    assert sc["history"]["artifact_chars_over_budget"]["B0"] > 16
    assert sc["notes"] and sc["plexus_changes"]
    assert doc["summary"]["l2_scale_accuracy_pct"] == {"B0": 83.3, "B1": 88.9, "B2": 63.9, "P": 100.0}


def test_l2_scale_honesty_travels_with_the_layer_verbatim(doc):
    src = json.loads(
        (ROOT / "plexus" / "demo_data" / "crucible" / "l2_scale" / "latest-full.json").read_text(
            encoding="utf-8"
        )
    )
    assert doc["layers"]["L2_scale"]["honesty"] == src["honesty"]
    assert all(h in doc["honesty"] for h in src["honesty"])
    assert any("NOT in this set" in h for h in src["honesty"])


def _all():
    from plexus.crucible.combine import (
        DEFAULT_B1H,
        DEFAULT_BASE,
        DEFAULT_C7X,
        DEFAULT_L2,
        DEFAULT_L2_SCALE,
        DEFAULT_L6,
        combine,
        render,
    )

    return render(combine(DEFAULT_BASE, DEFAULT_L2, DEFAULT_L2_SCALE, DEFAULT_B1H, DEFAULT_L6, DEFAULT_C7X))


def test_combined_file_is_exactly_the_merge_of_its_parts():
    assert ALL.read_text(encoding="utf-8") == _all(), (
        "latest-all.json is stale: run `python -m plexus.crucible.combine` and copy it to "
        "plexus-view/src/fixtures/results.real.json"
    )


def test_combine_does_not_touch_its_inputs(tmp_path):
    from plexus.crucible.combine import (
        DEFAULT_B1H,
        DEFAULT_BASE,
        DEFAULT_C7X,
        DEFAULT_L2,
        DEFAULT_L2_SCALE,
        main,
    )

    parts = (DEFAULT_BASE, DEFAULT_L2, DEFAULT_L2_SCALE, DEFAULT_B1H, DEFAULT_C7X)
    before = [p.read_bytes() for p in parts]
    out = tmp_path / "all.json"
    assert main(["--out", str(out)]) == 0
    assert main(["--out", str(out), "--check"]) == 0
    assert main(["--out", str(out), "--l2", "none", "--check"]) == 1  # different parts, different file
    assert before == [p.read_bytes() for p in parts]
    assert out.read_bytes() == ALL.read_bytes()


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


def test_b1h_c7x_and_l6_are_in_by_default_and_can_be_left_out(tmp_path):
    from plexus.crucible.combine import (
        DEFAULT_BASE,
        DEFAULT_L2,
        DEFAULT_L2_SCALE,
        combine,
        main,
        render,
    )

    full = json.loads(ALL.read_text(encoding="utf-8"))
    assert full["run"]["layers"][-3:] == ["B1h", "C7x", "L6"]
    assert full["layers"]["B1h"]["layers"]["L2"]["arm"]["accuracy"]["correct"] == 43
    assert full["layers"]["B1h"]["layers"]["L2_scale"]["arm"]["accuracy"]["correct"] == 36
    assert full["layers"]["C7x"]["arms"]["P"]["metrics"]["false_merges"] == 0
    assert full["layers"]["L6"]["summary"]["A"]["det"]["B1h"] == "24/24"
    assert full["layers"]["L6"]["summary"]["A"]["postfix"]["P-product-service"]["strict"] == "24/24"
    assert full["layers"]["L6"]["summary"]["F"]["postfix"]["P"]["orphans"] == 0
    # the pre-P9 five-layer file is still one flag away
    out = tmp_path / "old.json"
    assert main(["--out", str(out), "--b1h", "none", "--c7x", "none", "--l6", "none"]) == 0
    old = json.loads(out.read_text(encoding="utf-8"))
    assert old["run"]["layers"] == ["L1", "L4", "ablation", "L2", "L2_scale"]
    assert render(combine(DEFAULT_BASE, DEFAULT_L2, DEFAULT_L2_SCALE)) == out.read_text(encoding="utf-8")
    assert _all() == _all()  # deterministic
