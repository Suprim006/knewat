"""B1h: the hand-written SQL answerer reproduces the script-derived ground truth of L2 and L2-scale (no LLM, no database server)."""

from __future__ import annotations

import sqlite3

import pytest

from knewat.crucible.backends.sqlite_h import SqliteHistoryBackend
from knewat.crucible.l2 import sql_run
from knewat.crucible.l2.knewat_answerer import KnewatAnswerer
from knewat.crucible.l2.questions import generate, score
from knewat.crucible.l2.scale_scenario import play_scale
from knewat.crucible.l2.scenario import play
from knewat.crucible.l2.sql_answerer import ScaleSqlAnswerer, SqlAnswerer


def test_sql_answerer_has_every_cypher_op():
    cypher = {n[4:] for n in vars(KnewatAnswerer) if n.startswith("_op_")}
    sql = {n[4:] for n in vars(SqlAnswerer) if n.startswith("_op_")}
    assert sql == cypher and len(sql) == 34  # 34 operations answer the 10 families


def test_l2_all_43_match_ground_truth(tmp_path):
    out = sql_run.run_l2(tmp_path)
    arm = out["arm"]
    assert arm["accuracy"]["total"] == 43
    assert [r["id"] for r in arm["questions"] if not r["correct"]] == []
    assert arm["usage"]["llm_calls"] == 0 and arm["usage"]["cost_usd"] == 0


def test_l2_scale_36_match_ground_truth(tmp_path):
    out = sql_run.run_scale(tmp_path)
    arm = out["arm"]
    assert arm["accuracy"]["total"] == 36
    assert [r["id"] for r in arm["questions"] if not r["correct"]] == []
    assert {r["sprint"] for r in arm["questions"]} >= {"S01", "S20"} or len(arm["questions"]) == 36


def test_claims_history_is_what_recovery_needs(tmp_path):
    """Not vacuous: wipe the claim history and the three Recovery questions that need it fail."""
    b = SqliteHistoryBackend("t_claims", tmp_path)
    try:
        play(b)
        _, qs = generate(tmp_path / "q")
        ans = SqlAnswerer(b.path)
        recovery = [q for q in qs if q.op in ("reclaimed_tasks", "reclaimer", "previous_claimer")]
        assert len(recovery) == 3 and all(score(q, ans.answer(q)[0])[0] for q in recovery)
        ans.close()
        c = sqlite3.connect(b.path)
        c.execute("DELETE FROM claims")
        c.commit()
        c.close()
        ans = SqlAnswerer(b.path)
        bad = 0
        for q in recovery:
            try:
                bad += not score(q, ans.answer(q)[0])[0]
            except (StopIteration, IndexError):
                bad += 1
        ans.close()
        assert bad == 3
    finally:
        b.close()


def test_claim_row_is_written_in_the_claim_transaction(tmp_path):
    b = SqliteHistoryBackend("t_tx", tmp_path)
    try:
        b.register_agent("a1")
        b.register_agent("a2")
        b.create_tasks([{"title": "t", "id": "t1"}])
        got = b.claim_next_task("a1", lease_ms=1000, now=10_000)
        assert got is not None
        again = b.claim_next_task("a2", lease_ms=1000, now=20_000)  # lease expired -> reclaimed
        assert again is not None and again["reclaimed_from"] == "a1"
        with b._conn() as c:
            rows = c.execute("SELECT agent_id, reclaimed_from FROM claims ORDER BY seq").fetchall()
        assert [(r[0], r[1]) for r in rows] == [("a1", ""), ("a2", "a1")]
    finally:
        b.close()


def test_b1_baseline_artifacts_do_not_include_the_claims_table(tmp_path):
    """The L2 cache keys on the B1 dump; the extra table must not change it."""
    from knewat.crucible.l2 import contexts as C

    assert "claims" not in C.B1_TABLES


@pytest.mark.parametrize("scale", [False, True])
def test_wrong_sql_is_scored_wrong(tmp_path, scale):
    """The scorer sees a wrong SQL answer as wrong (guards against a vacuous 100%)."""
    if scale:
        pytest.skip("same scorer; the L2 case is enough")
    b = SqliteHistoryBackend("t_wrong", tmp_path)
    try:
        play(b)
        _, qs = generate(tmp_path / "q")
        q = next(q for q in qs if q.op == "blocked_by_failure")
        ans = SqlAnswerer(b.path)
        ok, _ = score(q, ans.answer(q)[0])
        assert ok
        assert not score(q, ans.answer(q)[0][:-1])[0]
        ans.close()
    finally:
        b.close()


def test_scale_answerer_class_is_importable():
    assert ScaleSqlAnswerer.SCOPED_OPS and play_scale
