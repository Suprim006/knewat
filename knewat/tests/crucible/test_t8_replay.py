"""The $0 trial-8 replay (knewat.crucible.t8_replay): the memo is void, C1 and P1 stay, C2 and C3 go."""

from __future__ import annotations

import json

import pytest

from knewat.crucible import t8_replay

from ..conftest import TEST_DB_PORT


@pytest.fixture
async def replay(client, tmp_path):
    return {r["scenario"]: r for r in await t8_replay.amain(TEST_DB_PORT, tmp_path)}, tmp_path


@pytest.mark.parametrize("scenario", ["source_ids", "corroboration"])
async def test_the_memo_retraction_keeps_c1_and_p1_and_hides_c2_and_c3(replay, scenario):
    r = replay[0][scenario]
    q = r["quarantine_memo"]
    assert q["hidden"] == ["C2", "C3"]
    assert q["corroborated"] == [{"fact": "C1", "other_sources": ["spec"]}]
    assert q["status"] == {"C1": "active", "C2": "quarantined", "C3": "quarantined", "P1": "active"}
    assert q["recalled"] == ["C1", "P1"]
    assert r["release_memo"]["restored"] == ["C2", "C3"]
    assert set(r["release_memo"]["status"].values()) == {"active"}
    f = r["forget_memo"]
    assert f["forgotten"] == ["C2", "C3"]
    assert f["unlinked"] == [{"fact": "C1", "other_sources": ["spec"]}]
    assert f["status"] == {"C1": "active", "C2": "forgotten", "C3": "forgotten", "P1": "active"}
    assert f["c1_sources"] == ["spec"] and f["recalled"] == ["C1", "P1"]


async def test_a_duplicate_assert_from_the_spec_corroborated_c1(replay):
    r = replay[0]["corroboration"]
    assert r["session1"]["second_assert_same_fact"] is True
    assert r["session1"]["second_assert"]["sources_added"] and r["after_session1"]["c1_sources"] == [
        "memo",
        "spec",
    ]
    assert replay[0]["source_ids"]["after_session1"]["c1_sources"] == ["memo", "spec"]


async def test_the_control_shows_what_trial_8_wrote_gets_hidden(replay):
    q = replay[0]["single_source"]["quarantine_memo"]
    assert q["hidden"] == ["C1", "C2", "C3"] and q["corroborated"] == []  # the graph names the memo only


async def test_the_replay_writes_its_results(replay):
    _, out = replay
    assert [r["scenario"] for r in json.loads((out / "results.json").read_text(encoding="utf-8"))] == list(
        t8_replay.SCENARIOS
    )
    assert "| source_ids |" in (out / "results.md").read_text(encoding="utf-8")
