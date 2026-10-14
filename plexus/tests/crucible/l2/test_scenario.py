"""The L2 scenario player: same story on every arm, same turns as the P3 recording, same texts as scripted.py."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from plexus.crucible.l2.scenario import TURNS, decision_label, fact_label, play

ROOT = Path(__file__).resolve().parents[3]
L2_ONLY = ("ingest-forum-post", "forget-forum-post", "ext-project-facts")


def _strip_ids(led) -> dict:
    d = led.to_json()
    d.pop("arm")
    for key in ("facts", "decisions", "sources", "artifacts"):
        for row in d[key]:
            row.pop("id", None)
    return d


def test_turn_order_matches_the_p3_recording():
    meta = json.loads((ROOT / "demo_data/recordings/acme-scripted/meta.json").read_text(encoding="utf-8"))
    recorded = [(t["kind"], t["agent"], t["name"], t["reclaim_from"]) for t in meta["turns"]]
    ours = [t for t in TURNS if t[2] not in L2_ONLY]
    assert ours == recorded  # the recording has exactly these turns; L2 only adds the three above


def test_texts_come_from_the_p3_script():
    src = (ROOT / "src/plexus/demo/scripted.py").read_text(encoding="utf-8")
    mine = (ROOT / "src/plexus/crucible/l2/scenario.py").read_text(encoding="utf-8")
    pattern = (
        r'"((?:Build|Adopt|Use JWT|Spec approved|Evaluate|Drafting|Endpoint draft|Style guide|Schema:'
        r'|Endpoint design|CRUD spec|Release bundle|Updated for)[^"]{8,})"'
    )
    phrases = re.findall(pattern, mine)
    assert len(phrases) >= 9
    for p in phrases:
        assert p[:40] in src, p
    for uri in re.findall(r'"(artifacts/[a-z0-9.\-]+)"', mine):
        assert uri in src


def test_labels():
    assert fact_label("api_version", "v1") == "api_version=v1"
    assert decision_label("Adopt style guide v2: the API version is now v2") == "adopt style guide v2"
    assert decision_label("Use PostgreSQL 16 for the notes") == "use postgresql 16 for"


@pytest.mark.parametrize("arm", ["B0", "B1", "B2"])
def test_play_counts(arm, opened):
    led = play(opened(arm))
    assert len(led.decisions) == 6 and len(led.handoffs) == 4 and len(led.tasks) == 12
    assert sum(len(f["superseded"]) for f in led.facts) == 1
    assert sorted(f["label"] for f in led.facts if f["contradicts"]) == [
        "auth_method=API key in X-Api-Key header",
        "database=MongoDB 4",
    ]
    assert [c["task_id"] for c in led.claims if c["reclaimed_from"]] == ["t03-design-endpoints"]
    assert led.forgotten[0]["fact_labels"] == ["database=MongoDB 4"]
    assert [e["event"] for e in led.events][:2] == ["kill_builder", "reclaim"]


def test_every_arm_tells_the_same_story(opened):
    ledgers = {arm: _strip_ids(play(opened(arm))) for arm in ("B0", "B1", "B2")}
    assert ledgers["B0"] == ledgers["B1"] == ledgers["B2"]


@pytest.mark.integration
def test_plexus_arm_tells_the_same_story(opened):
    assert _strip_ids(play(opened("P"))) == _strip_ids(play(opened("B1")))
