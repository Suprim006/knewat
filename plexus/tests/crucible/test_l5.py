"""Crucible L5 at toy size (no LLM). The full run is `python -m plexus.crucible.l5`; its design is pre-registered in
docs/BASELINE.md. These tests check that the harness measures what it claims to, not the headline numbers."""

from __future__ import annotations

import json

import pytest

from plexus.crucible.l5 import report as R
from plexus.crucible.l5.staleness import KINDS, build_repo, run_arm, segments
from plexus.embed import HashEmbedder

from .conftest import DB_HOST, DB_PORT


@pytest.fixture(scope="module")
def emb():
    return HashEmbedder()


@pytest.fixture
def l5_client(client):  # the shared session client of tests/conftest.py
    return client


def test_segments_ignore_trailing_whitespace_but_see_edits():
    a = "def f():\n    '''d'''\n    return 1\n"
    assert segments(a) == segments(a.replace("return 1", "return 1   ").replace("'''d'''", "'''d'''  "))
    assert segments(a) != segments(a.replace("return 1", "return 2"))
    assert segments(a) == segments(a.replace("\n", "\r\n"))


def test_the_scripted_repo_has_every_kind_and_the_script_agrees_with_the_ast(tmp_path):
    repo = build_repo(tmp_path / "r", modules=3, funcs=3, commits=10)
    assert {c.kind for c in repo.commits} == set(KINDS) and len(repo.commits) == 10
    assert len(repo.facts) == 9
    for c in repo.commits:  # build_repo itself raises when the two differ; re-assert the shape
        assert c.truth == c.edited
        if c.kind in ("add", "module-comment", "whitespace", "reorder"):
            assert c.truth == set()
        if c.kind in ("value", "sibling", "docstring", "delete"):
            assert c.truth


def test_the_repo_is_deterministic(tmp_path):
    a = build_repo(tmp_path / "a", modules=3, funcs=3, commits=10)
    b = build_repo(tmp_path / "b", modules=3, funcs=3, commits=10)
    assert [c.kind for c in a.commits] == [c.kind for c in b.commits]
    assert [sorted(c.truth) for c in a.commits] == [sorted(c.truth) for c in b.commits]
    assert [c.sha for c in a.commits] == [c.sha for c in b.commits]  # fixed author, dates and content


def test_staleness_arms(tmp_path, l5_client, emb):
    repo = build_repo(tmp_path / "r", modules=3, funcs=3, commits=10)
    total = sum(len(c.truth) for c in repo.commits)
    assert total > 0
    s = run_arm("S", repo, l5_client, emb)
    f = run_arm("F", repo, l5_client, emb)
    n = run_arm("N", repo, l5_client, emb)
    # symbol-level anchors flag exactly what changed
    assert (s.fp, s.fn, s.tp) == (0, 0, total) and s.unflagged_returned == 0
    assert s.precision == 1.0 and s.recall == 1.0
    # file-level anchors never miss but over-flag (the add / comment / whitespace / reorder commits flag nothing true)
    assert f.fn == 0 and f.tp == total and f.fp > 0 and f.precision < 1.0 and f.unflagged_returned == 0
    assert all(
        c["flagged"] > 0 and c["tp"] == 0
        for c in f.per_commit
        if c["kind"] in ("add", "whitespace", "reorder")
    )
    # no anchors: nothing is flagged and every stale fact comes back unflagged
    assert (n.tp, n.fp) == (0, 0) and n.fn == total and n.recall == 0.0 and n.precision is None
    assert n.unflagged_returned + n.not_returned == total and n.unflagged_returned > 0


def test_forgetting_toy_run(l5_client, emb):
    from plexus.crucible.l5.forgetting import run_forgetting

    res = run_forgetting(l5_client, emb, k_sprints=1, noise_mult=2, days=20)
    assert res["classes"]["critical"] > 0 and res["noise_facts"] > 0
    assert set(res["modes"]) == {"off", "on", "on+sweep"}
    sw = res["sweep"]
    assert sw["fact_nodes_before"] == sw["fact_nodes_after"], "a sweep never deletes"
    assert sw["moved_by_class"]["critical"] == 0 and sw["dry_run_critical_candidates"] == 0
    for mode in ("on", "on+sweep"):
        assert res["modes"][mode]["critical_probe_loss"] == 0
    for m in res["modes"].values():
        assert 0 <= m["noise_share"] <= 1 and m["chars_per_recall"] > 0
        assert m["recall"]["all"]["n"] == res["history"]["real_active_facts"]


def test_forgetting_d013_modes_toy(l5_client, emb):
    from plexus.crucible.l5.forgetting import run_forgetting

    names = ("off", "on-mult", "kw-fix", "sep", "sep+add", "sep-entity")
    res = run_forgetting(l5_client, emb, k_sprints=2, noise_mult=2, modes=names, burst=True)
    assert set(res["modes"]) == set(names)
    assert res["config"]["burst"] is True and list(res["config"]["modes"]) == list(names)
    for name, m in res["modes"].items():
        for k in (1, 3, 5):
            assert 0 <= m["recall"]["all"][f"recall@{k}"] <= 1
        assert m["above_same_entity"] + m["above_other_entity"] == sum(m["ranked_above_target"].values())
        assert isinstance(m["entity_read_ms"], float) == (name in ("sep", "sep+add", "sep-entity"))
        assert {"p10", "p25", "p50", "p75", "p90", "n"} <= set(m["gap12"])
    assert res["modes"]["off"]["gap12"]["n"] >= 1
    crit = R.criteria({"forgetting": res})
    assert any(k["id"].startswith("L5b-D013 sep recall@1") for k in crit)
    assert "L5b-D013 kw-fix recall@1 (report only)" in {k["id"] for k in crit}
    assert "PC sep recall@1 >= 0.95" in {k["id"] for k in crit}, (
        "the predicate-cue criteria need sep + sep-entity"
    )


def test_hub_variant_toy(l5_client, emb, tmp_path):
    """The plan's §5.3 hub world runs end to end on the hash embedder (toy: every arm, criteria present)."""
    from plexus.crucible.l5 import hub as H

    res = H.run_hub(l5_client, emb)
    assert res["world"]["facts"] == H.HUB_FACTS + H.N_OTHERS * H.FACTS_PER_OTHER
    assert res["world"]["hub_fan_resolved"] == H.HUB_FACTS, "the hub is resolved by name with its full fan"
    assert 1.5 <= res["world"]["predicate_fan_mean"] <= 3.0
    assert set(res["arms"]) == set(H.ARMS)
    for m in res["arms"].values():
        assert 0 <= m["recall@1"] <= m["recall@5"] <= 1 and m["statements_per_probe"] >= 2
    assert (
        res["arms"]["off"]["entity_facts_added_mean"] == 0 and res["arms"]["sep"]["statements_per_probe"] >= 4
    )
    res["criteria"] = H.hub_criteria(res)
    assert {k["id"] for k in res["criteria"]} >= {"hub: sep recall@1 >= 0.90 (plan §5.3)"}
    text = H.render_hub(res)
    assert "| sep |" in text and "| sep-flat |" in text


def test_forgetting_sql_arm_toy(l5_client, emb, tmp_path):
    """Plan §5.4: the SQL arm (export + three statements) runs next to Plexus; activation agrees for every fact,
    the retrieval-only mode (`off`) finds the same target at rank 1 for every probe, and the arm counts its
    statements and SQL lines."""
    from plexus.crucible.l5 import sql_arm
    from plexus.crucible.l5.forgetting import run_forgetting

    res = run_forgetting(
        l5_client,
        emb,
        k_sprints=2,
        noise_mult=2,
        modes=("off", "sep+mult"),
        sql=True,
        sql_path=str(tmp_path / "l5b.sqlite"),
    )
    assert set(res["sql_modes"]) == {"off", "sep+mult"}
    fid = res["sql_arm"]["activation_fidelity"]
    assert fid["facts"] > 0 and fid["disagreements"] == 0, fid
    assert res["sql_arm"]["sql_lines"] == sql_arm.sql_lines() > 50
    pr = res["sql_pairs"]["off"]
    # the hash embedder produces exact distance ties, so only rank-1 agreement is asserted on the toy world
    assert pr["same_top1"] == pr["n"] and pr["only_plexus_at1"] == pr["only_sql_at1"] == 0
    assert res["sql_modes"]["sep+mult"]["statements_per_probe"] >= 3.0
    assert res["modes"]["sep+mult"]["statements_per_probe"] >= 4.0
    assert res["sql_modes"]["off"]["probe_ms"]["n"] == pr["n"]


def test_forgetting_unknown_mode(l5_client, emb):
    from plexus.crucible.l5.forgetting import run_forgetting

    with pytest.raises(ValueError):
        run_forgetting(l5_client, emb, k_sprints=1, modes=("nope",))


def test_run_all_writes_results_and_report(tmp_path, l5_client):
    out = R.run_all(l5_client, "hash", tmp_path, sprints=1, noise=1, modules=3, funcs=3, commits=8)
    res = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert res["llm_calls"] == 0 and {"staleness", "forgetting", "criteria"} <= set(res)
    assert all(k["ok"] for k in res["criteria"] if k["hard"]), res["criteria"]
    text = (out / "report.md").read_text(encoding="utf-8")
    assert "## L5a: staleness" in text and "## L5b: forgetting" in text and "PASS" in text
    assert DB_HOST and DB_PORT
