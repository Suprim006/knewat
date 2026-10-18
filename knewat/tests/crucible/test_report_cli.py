"""CLI + results.json + report.md."""

from __future__ import annotations

import json

import pytest

from knewat.crucible import cli
from knewat.crucible.report import render

from .conftest import DB_HOST, DB_PORT


def check_schema(res: dict) -> None:
    """The contract the View Results page relies on (see knewat.crucible.results)."""
    assert res["schema_version"] == 1 and res["kind"] == "crucible-results"
    assert {"id", "started_at", "finished_at", "duration_s", "quick", "command", "layers"} <= set(res["run"])
    assert {"python", "platform", "in_docker", "git_commit", "embedder", "falkordb"} <= set(
        res["environment"]
    )
    assert "arms" in res["config"]
    for arm, info in res["arms"].items():
        assert {"label", "represents", "description", "isolation", "capabilities"} <= set(info), arm
    layers = res["layers"]
    if "L1" in layers:
        assert res["config"]["seeds"] and "l1" in res["config"]
        for tid, spec in layers["L1"]["tests"].items():
            assert {"title", "metric", "bar"} <= set(spec), tid
        for arm, a in layers["L1"]["arms"].items():
            for tid, r in a["tests"].items():
                assert {
                    "runs",
                    "runs_passed",
                    "passed",
                    "unsupported",
                    "violations_total",
                    "metrics",
                    "runs_detail",
                } <= set(r)
                for d in r["runs_detail"]:
                    assert {"seed", "params", "passed", "violations", "metrics"} <= set(d), (arm, tid)
        assert res["summary"]["l1_matrix"]
    if "L4" in layers:
        assert {"claim_sweep", "recall_sweep", "tenant_sweep"} <= set(layers["L4"])
        assert "l4" in res["config"]
        for p in layers["L4"]["claim_sweep"]:
            assert {"arm", "workers", "throughput_ops_s", "claim", "heartbeat", "complete"} <= set(p)
            assert {"p50_ms", "p95_ms", "p99_ms"} <= set(p["claim"])
    if "ablation" in layers:
        assert {"capabilities", "summary", "l1_rerun", "stripped_relationship_types"} <= set(
            layers["ablation"]
        )
    assert res["honesty"]


def run_cli(tmp_path, *args: str, sub: str = "results") -> tuple[int, dict, str]:
    out = tmp_path / sub
    code = cli.main(
        [*args, "--out", str(out), "--embedder", "hash", "--host", DB_HOST, "--port", str(DB_PORT)]
    )
    latest = (
        json.loads((out / "latest.json").read_text(encoding="utf-8"))
        if (out / "latest.json").exists()
        else {}
    )
    dirs = [d for d in out.iterdir() if d.is_dir()] if out.exists() else []
    report = (dirs[0] / "report.md").read_text(encoding="utf-8") if dirs else ""
    if dirs:
        assert json.loads((dirs[0] / "results.json").read_text(encoding="utf-8")) == latest
    return code, latest, report


def test_l1_quick_writes_results_and_report(tmp_path):
    code, res, report = run_cli(
        tmp_path, "l1", "--quick", "--arms", "B0,B1", "--tests", "C1,C6", "--reps", "1"
    )
    assert code == 0
    check_schema(res)
    assert res["run"]["quick"] is True and res["run"]["layers"] == ["L1"]
    assert set(res["layers"]["L1"]["arms"]) == {"B0", "B1"}
    assert res["layers"]["L1"]["arms"]["B1"]["tests"]["C1"]["passed"] is True
    assert "# Crucible report" in report and "C1" in report and "QUICK run" in report
    assert report == render(res)


def test_l4_quick_without_a_database(tmp_path):
    code, res, report = run_cli(tmp_path, "l4", "--quick", "--arms", "B1", "--workers", "1,3")
    assert code == 0
    check_schema(res)
    pts = res["layers"]["L4"]["claim_sweep"]
    assert [p["workers"] for p in pts] == [1, 3] and all(
        p["arm"] == "B1" and p["error_count"] == 0 for p in pts
    )
    assert all(p["tasks_done_in_store"] == p["tasks"] for p in pts)
    assert res["layers"]["L4"]["tenant_sweep"] and "Throughput" in report


def test_unknown_arm_or_test_is_rejected(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(["l1", "--arms", "B9", "--out", str(tmp_path)])
    with pytest.raises(SystemExit):
        cli.main(["l1", "--tests", "C9", "--out", str(tmp_path)])


def test_unreachable_database_exits_2(tmp_path, monkeypatch):
    import redis

    def refuse(*a, **k):
        raise redis.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr(redis, "Redis", refuse)
    assert cli.main(["l1", "--arms", "P", "--port", "1", "--out", str(tmp_path), "--embedder", "hash"]) == 2


@pytest.mark.integration
def test_knewat_l1_and_ablation_through_the_cli(tmp_path):
    code, res, report = run_cli(
        tmp_path, "l1", "--quick", "--arms", "P", "--tests", "C1,C3,C5", "--reps", "1"
    )
    assert code == 0
    check_schema(res)
    assert res["environment"]["falkordb"]["reachable"] is True
    code, res, report = run_cli(tmp_path, "ablation", "--quick", sub="ablation")
    assert code == 0
    check_schema(res)
    s = res["layers"]["ablation"]["summary"]
    assert s["intact_all_pass"] and s["broken_by_ablation"] == s["capabilities_needing_edges"] > 0
    assert s["controls_unaffected"] == s["controls"] > 0
    assert "Ablation" in report


def test_rerun_replaces_only_the_named_cells_and_keeps_the_original(tmp_path):
    out = tmp_path / "r"
    common = ["--out", str(out), "--embedder", "hash", "--host", DB_HOST, "--port", str(DB_PORT)]
    assert cli.main(["l1", "--quick", "--arms", "B1", "--tests", "C1,C6", "--reps", "1", *common]) == 0
    base = next(d for d in out.iterdir() if d.is_dir())
    before = json.loads((base / "results.json").read_text(encoding="utf-8"))
    c6_before = before["layers"]["L1"]["arms"]["B1"]["tests"]["C6"]
    argv = ["rerun", "--base", str(base), "--cell", "L1:B1:C1", "--reason", "pool was too small", *common[2:]]
    assert cli.main(argv) == 0
    after = json.loads((base / "results.json").read_text(encoding="utf-8"))
    check_schema(after)
    assert after["layers"]["L1"]["arms"]["B1"]["tests"]["C6"] == c6_before
    (rr,) = after["run"]["reruns"]
    assert rr["cells"] == ["L1:B1:C1"] and rr["reason"] == "pool was too small"
    assert (
        rr["superseded"][0]["result"]["runs"] == before["layers"]["L1"]["arms"]["B1"]["tests"]["C1"]["runs"]
    )
    assert "Re-runs" in (base / "report.md").read_text(encoding="utf-8")
    assert cli.main(["rerun", "--base", str(base), *common[2:]]) == 2  # needs a cell and a reason


def test_wait_for_db_waits_while_loading_and_fails_fast_otherwise(monkeypatch):
    import redis

    calls = {"n": 0}

    class Fake:
        def __init__(self, *a, **k): ...
        def ping(self):
            return True

        def info(self, section):
            calls["n"] += 1
            return {"loading": 1 if calls["n"] < 3 else 0}

    monkeypatch.setattr(redis, "Redis", Fake)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    assert cli.wait_for_db("h", 1, 30) == "" and calls["n"] == 3
    calls["n"] = -(10**9)  # never finishes loading
    assert "still loading" in cli.wait_for_db("h", 1, 0)

    def refuse(*a, **k):
        raise redis.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr(redis, "Redis", refuse)
    assert cli.wait_for_db("h", 1, 30) == "connection refused"  # not a loading error: returns at once
