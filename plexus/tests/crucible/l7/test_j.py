"""Family J (concurrent session populations): unit tests of the session model + toy-size cells.

SQLite cells run anywhere; FalkorDB cells (marked integration through the ``client`` fixture) need
``PLEXUS_TEST_DB_PORT``.
"""

from __future__ import annotations

import json
import random
from collections import Counter

import pytest
from redis.exceptions import ResponseError

from plexus.crucible.api import ClaimConflict
from plexus.crucible.l7 import j
from plexus.crucible.l7.j_arms import SAdapter
from plexus.crucible.l7.j_session import (
    RECORDED_MIX,
    Rec,
    Session,
    TenantPool,
    classify_error,
    load_sequences,
    preload,
)
from tests.conftest import TEST_DB_HOST, TEST_DB_PORT


# ------------------------------------------------------------------------------------------------ session model
def test_sequences_reproduce_the_preregistered_mix():
    seqs = load_sequences()
    assert sorted(len(s) for s in seqs.values()) == [3, 7, 7, 25, 25, 33]
    c = Counter(t for s in seqs.values() for t in s)
    assert sum(c.values()) == 100
    for tool, pct in RECORDED_MIX.items():
        assert abs(c[tool] - pct) <= 1, (tool, c[tool], pct)  # the doc rounds to whole percent


@pytest.mark.parametrize(
    ("msg", "cls"),
    [
        ("database is locked", "locked"),
        ("ResponseError: Max pending queries exceeded", "max_pending"),
        ("Query timed out", "timeout"),
        ("No connection available.", "pool"),
        ("Connection reset by peer", "connection"),
        ("unknown origin id: x", "unknown_ref"),
        ("boom", "other"),
    ],
)
def test_classify_error(msg, cls):
    assert classify_error(RuntimeError(msg)) == cls


class FakeAdapter:
    """In-memory adapter: records calls; claim returns tasks from a list (or None)."""

    def __init__(self, tasks=0, fail_start=False, conflict=False):
        self.log = []
        self.tasks = [{"id": f"x{i}", "version": 1} for i in range(tasks)]
        self.fail_start, self.conflict = fail_start, conflict

    def __getattr__(self, name):
        def call(*a, **k):
            self.log.append(name)
            if name == "start_session":
                if self.fail_start:
                    raise RuntimeError("database is locked")
                return "sid"
            if name == "claim":
                return self.tasks.pop() if self.tasks else None
            if name == "complete":
                if self.conflict:
                    raise ClaimConflict("lost")
                return ["art1"]
            if name in ("recall",):
                return ["f1"]
            if name in ("assert_fact", "add_source", "record_decision", "handoff", "create_tasks"):
                return f"id-{name}"
            return None

        return call


def _pool():
    return TenantPool.from_manifest(
        {
            "facts": ["f0"],
            "sources": ["s0"],
            "decisions": ["d0"],
            "artifacts": ["a0"],
            "anchor_tasks": ["t0"],
            "agents": ["ag"],
        }
    )


def _run(adapter, seq, trav=False, seed=1):
    rec = Rec()
    Session(adapter, _pool(), random.Random(seed), "agentx", seq, trav, rec, lambda: True, lambda: True).run()
    return rec


def test_complete_follows_a_successful_claim_and_empty_claim_refills():
    seq = ["start_session", "claim_next_task", "complete_task", "claim_next_task", "complete_task"]
    a = FakeAdapter(tasks=1)
    rec = _run(a, seq)
    assert a.log.count("complete") == 1  # the second claim found nothing, so its complete is skipped
    assert a.log.count("create_tasks") == 1  # refill after the empty claim
    names = [c[0] for c in rec.calls]
    assert names.count("create_tasks_refill") == 1
    assert [c[3] for c in rec.calls if c[0] == "claim_next_task"] == ["ok", "no_task"]
    assert rec.skipped_complete == 1 and rec.sessions == 1


def test_claim_conflict_is_an_outcome_and_start_failure_aborts_the_session():
    rec = _run(FakeAdapter(tasks=1, conflict=True), ["start_session", "claim_next_task", "complete_task"])
    assert rec.calls[-1][3] == "claim_conflict"
    rec = _run(FakeAdapter(fail_start=True), ["start_session", "recall", "recall"])
    assert [c[3] for c in rec.calls] == ["err:locked"] and rec.sessions == 0
    assert rec.err_samples["err:locked"]


def test_trav_mix_replaces_about_ten_percent_and_never_the_first_call():
    seqs = list(load_sequences().values())
    n = trav = 0
    for s in range(300):
        a = FakeAdapter(tasks=50)
        seq = seqs[s % len(seqs)]
        _run(a, seq, trav=True, seed=s)
        n += len(seq) - 1
        trav += a.log.count("why") + a.log.count("impact")
        assert a.log[0] == "start_session"
    assert 0.07 < trav / n < 0.13


def test_replay_is_deterministic_per_seed():
    seq = load_sequences()["acme-claude-sonnet/researcher"]
    a, b = FakeAdapter(tasks=9), FakeAdapter(tasks=9)
    _run(a, seq, seed=5)
    _run(b, seq, seed=5)
    assert a.log == b.log


# ------------------------------------------------------------------------------------------------ aggregation
def test_aggregate_throughput_latency_and_error_classes():
    calls = [
        ["recall", -1.0, 5.0, "ok"],  # warm-up leftover: excluded
        ["recall", 0.5, 10.0, "ok"],
        ["recall", 1.0, 30.0, "ok"],
        ["claim_next_task", 1.5, 20.0, "no_task"],
        ["complete_task", 2.0, 15.0, "claim_conflict"],
        ["assert_fact", 2.5, 120000.0, "err:locked"],
        ["assert_fact", 3.0, 9.0, "err:max_pending"],
        ["recall", 3.9, 500.0, "ok"],  # finishes after the window: attempted, not completed
        ["recall", -0.4, 900.0, "ok"],  # started in warm-up, finished 0.5 s into the window: counts
    ]
    r = j.aggregate(calls, 4.0)
    assert r["attempted"] == 8 and r["completed"] == 5 and r["errors"] == 2 and r["late_finishers"] == 2
    assert r["throughput_calls_s"] == 1.25
    assert r["errors_by_class"]["locked"] == 1 and r["errors_by_class"]["max_pending"] == 1
    assert r["domain_outcomes"] == {"no_task": 1, "claim_conflict": 1}
    assert r["per_tool"]["recall"]["lat_ms"]["n"] == 4
    assert r["per_tool"]["assert_fact"]["lat_ms"]["n"] == 0  # errors are not in the success latency
    assert r["per_tool"]["assert_fact"]["lat_all_ms"]["max"] == 120000.0


def test_layout_and_grid_arithmetic():
    assert [j.n_tenants(p, "J-team") for p in (2, 20, 200, 1000)] == [1, 4, 40, 200]
    assert all(j.n_tenants(p, "J-one") == 1 for p in (2, 1000))
    assert [j.tenant_of(s, "J-team") for s in (0, 4, 5, 19)] == [0, 0, 1, 3]
    args = j.make_parser().parse_args(["run", "--port", "1", "--scale", "full"])
    args.pops, args.reps, args.seconds, args.warmup = [2, 20, 200, 1000], 3, 30.0, 5.0
    args.mixes, args.extra = ["J-real", "J-trav"], []
    assert len(j.plan(args)) == 4 * 2 * 3 * 2 * 3


# ------------------------------------------------------------------------------------------------ S-file adapter
def test_sqlite_adapter_preload_and_all_operations(tmp_path):
    a = SAdapter("jt1", str(tmp_path), trav_index=True)
    man = preload(a, "jt1", 1, seed_tasks=30)
    assert len(man["facts"]) == 24 and len(man["artifacts"]) == 4 and len(man["decisions"]) == 6
    pool = TenantPool.from_manifest(man)
    seqs = load_sequences()
    rec = Rec()
    rng = random.Random(3)
    for seq in seqs.values():
        Session(a, pool, rng, f"w{rng.random()}", seq, True, rec, lambda: True, lambda: True).run()
    bad = [c for c in rec.calls if c[3].startswith("err:")]
    assert not bad, (bad[:3], rec.err_samples)
    a.verify_artifact("seedagent1", man["artifacts"][0])
    with a.b._conn() as c:
        assert (
            c.execute(
                "SELECT independent FROM artifact_verifications WHERE agent_id='seedagent1' AND artifact_id=?",
                (man["artifacts"][0],),
            ).fetchone()[0]
            == 1
        )
        assert c.execute("SELECT count(*) FROM sessions").fetchone()[0] >= 6
    a.impact("x", "fact", man["facts"][0])
    a.impact("x", "source", man["sources"][0])
    a.why("x", man["decisions"][0])
    st = a.store_stats()
    assert st["file_bytes"] > 0 and st["rows_facts"] >= 24
    a.drop()
    assert not (tmp_path / "B1" / "jt1").exists()


def _toy_cell(arm, tmp_path, port, **kw):
    cell = j.run_cell(
        arm, kw.pop("pop", 2), kw.pop("layout", "J-team"), kw.pop("mix", "J-real"), 0,
        host=TEST_DB_HOST, port=port, seconds=2.0, warmup=0.5, grace=20.0, work=tmp_path, tag=kw.pop("tag", "tt0"),
        per_session_tasks=10, task_cap=50, ready_timeout=120.0, **kw,
    )  # fmt: skip
    assert "failed" not in cell, cell.get("failed")
    assert cell["attempted"] > 20 and cell["throughput_calls_s"] > 0
    assert cell["errors"] == 0, cell["error_samples"]
    assert cell["drivers"]["cpu_s_total"] > 0 and cell["drivers"]["peak_working_set_mb_sum"] > 0
    assert cell["procs"] == 2 and cell["tenants"] == 1
    assert cell["mix_share_pct"]["start_session"] > 5
    json.dumps(cell)  # JSON-clean
    return cell


def test_toy_cell_sqlite_and_report(tmp_path):
    cell = _toy_cell("S-file", tmp_path, 0, tag="tts1")
    assert cell["store"]["total_bytes_all_tenants"] > 0
    assert not (tmp_path / "tts1").exists()  # cell files deleted
    trav = _toy_cell("S-file", tmp_path, 0, mix="J-trav", tag="tts2")
    assert "why" in trav["tool_counts"] or "impact" in trav["tool_counts"]
    doc = {
        "run": {"id": "x-j"},
        "params": {"scale": "dev", "seconds": 2.0, "warmup": 0.5, "reps": 1},
        "cells": [cell, trav],
    }
    md = j.build_report(doc)
    assert "S-file" in md and "tput calls/s" in md and "S-shared" in md


def test_toy_cell_sqlite_failure_is_recorded_not_raised(tmp_path):
    cell = j.run_cell(
        "S-file", 2, "J-one", "J-real", 0, host=TEST_DB_HOST, port=0, seconds=1.0, warmup=0.2, grace=5.0,
        work=tmp_path, tag="ttf", ready_timeout=0.0,
    )  # fmt: skip
    assert cell["failed"]["stage"] == "ready" and "TimeoutError" in cell["failed"]["error"]
    assert not (tmp_path / "ttf").exists()


# ------------------------------------------------------------------------------------------------ F arms (need FalkorDB)
@pytest.mark.parametrize("arm", ["F-service", "F-mcp"])
def test_toy_cell_falkordb(arm, client, tmp_path):
    cell = _toy_cell(arm, tmp_path, TEST_DB_PORT, tag=f"ttf{arm[-3:]}".replace("-", ""))
    assert cell["falkordb_server"]["graph_cmd_calls"] > 0
    assert cell["store"]["per_tenant"][0]["nodes"] > 50
    # the cell's graph is gone
    from plexus.graph.tenancy import graph_name

    with pytest.raises(ResponseError, match="empty key"):
        client.graph(graph_name(f"j{cell['tag']}t0")).ro_query("MATCH (n) RETURN count(n)")


def test_toy_cell_falkordb_trav(client, tmp_path):
    """J-trav on F-mcp: exercises the product why / impact work functions through Runtime._run."""
    cell = _toy_cell("F-mcp", tmp_path, TEST_DB_PORT, mix="J-trav", tag="ttftr")
    assert "why" in cell["tool_counts"] and "impact" in cell["tool_counts"]
    assert cell["per_tool"]["why"]["status"].get("ok", 0) > 0
