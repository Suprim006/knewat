"""L2 at scale: the K-sprint scenario, the 40 questions, the BM25 selectors, the sprint-scoped Plexus answerer, the run.

No LLM anywhere: the CLI is the mocked ``fake_claude_l2.py``. Arm P needs a FalkorDB (``PLEXUS_TEST_DB_PORT``).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from plexus.crucible.api import BackendSpec
from plexus.crucible.backends import open_backend
from plexus.crucible.l2 import contexts as C
from plexus.crucible.l2 import scale_contexts as SC
from plexus.crucible.l2.llm import PROMPT_VERSION, cache_key
from plexus.crucible.l2.questions import FAMILIES, Question, score
from plexus.crucible.l2.scale_plexus import ScalePlexusAnswerer
from plexus.crucible.l2.scale_questions import (
    assign_sprints,
    build_scale_questions,
    generate_scale,
    load_scale_questions,
)
from plexus.crucible.l2.scale_run import (
    CONVENTIONS_SCALE,
    K_SPRINTS,
    PILOT_IDS,
    render_scale_report,
    run_scale,
    stratum_of,
)
from plexus.crucible.l2.scale_run import (
    PROMPT_VERSION as SCALE_PROMPT_VERSION,
)
from plexus.crucible.l2.scale_scenario import Sprint, play_scale
from plexus.crucible.l2.scenario import TURNS

FAKE = [sys.executable, str(Path(__file__).with_name("fake_claude_l2.py"))]
COMMITTED = Path(__file__).resolve().parents[3] / "demo_data/crucible/questions_scale.yaml"
DB_PORT = int(os.environ.get("PLEXUS_TEST_DB_PORT", "6310"))


@pytest.fixture(scope="module")
def truth(tmp_path_factory):
    return generate_scale(tmp_path_factory.mktemp("truth"), K_SPRINTS)


def test_committed_questions_are_what_the_scenario_generates(truth):
    _, fresh = truth
    committed = load_scale_questions(COMMITTED)
    assert [q.to_json() for q in committed] == [q.to_json() for q in fresh]


def test_forty_questions_ten_families_four_each(truth):
    _, qs = truth
    assert len(qs) == 40
    assert {f: sum(q.family == f for q in qs) for f in FAMILIES} == dict.fromkeys(FAMILIES, 4)
    assert [q.id for q in qs] == [f"Q{i:02d}" for i in range(1, 41)]
    for q in qs:  # every question names its sprint, and the args carry it
        tag = q.args["sprint"]
        assert q.text.startswith(f"In sprint {tag.upper()}: ")


def test_budget_reduction_drops_four_non_pilot_questions_one_per_family(truth):
    import random

    from plexus.crucible.l2.scale_run import FULL_DROPPED_IDS

    _, qs = truth
    fams = random.Random(20261016).sample(list(FAMILIES), 4)
    assert sorted([q.id for q in qs if q.family == f][3] for f in fams) == sorted(FULL_DROPPED_IDS)
    assert not set(FULL_DROPPED_IDS) & set(PILOT_IDS)


def test_sprints_are_sampled_across_the_history(truth):
    sl, qs = truth
    k = len(sl.sprints)
    by = {s: 0 for s in ("early", "middle", "late")}
    for q in qs:
        by[stratum_of(int(q.args["sprint"][1:]), k)] += 1
    assert min(by.values()) >= 12 and sum(by.values()) == 40
    assert assign_sprints(20, 40) == assign_sprints(20, 40)  # a pure function of (k, n, seed)
    assert len(set(assign_sprints(20, 40))) >= 18  # sprints are dealt round-robin, not drawn with replacement


def test_pilot_covers_five_families_and_all_strata(truth):
    sl, qs = truth
    pilot = [q for q in qs if q.id in PILOT_IDS]
    assert len(pilot) == 5 and len({q.family for q in pilot}) == 5
    assert {stratum_of(int(q.args["sprint"][1:]), len(sl.sprints)) for q in pilot} == {
        "early",
        "middle",
        "late",
    }


def test_sprints_are_distinguishable_and_labels_unique(truth):
    sl, _ = truth
    labels = [
        f["label"]
        for led in sl.ledgers
        for f in led.facts
        if f["scope"] in ("global",) and f["predicate"] != "purpose"
    ]
    keyed = {f["label"] for led in sl.ledgers for f in led.facts if f["predicate"] in ("api_version",)}
    assert len(keyed) == 2 * len(sl.sprints)  # every api_version label belongs to exactly one sprint
    api_keys = [
        f["label"] for led in sl.ledgers for f in led.facts if f["label"].startswith("auth_method=API key")
    ]
    assert len(set(api_keys)) == len(api_keys) == len(sl.sprints)
    decisions = [d["label"] for led in sl.ledgers for d in led.decisions]
    assert len(set(decisions)) == len(decisions) == 6 * len(sl.sprints)
    assert len(labels) > 0
    for sp, led in zip(sl.sprints, sl.ledgers, strict=True):
        assert all(t["id"].startswith(sp.p) for t in led.tasks)
        assert all(f"/{sp.low}/" in s["uri"] for s in led.sources)


def test_each_sprint_replays_the_acme_story(truth):
    sl, _ = truth
    for sp, led in zip(sl.sprints, sl.ledgers, strict=True):
        assert [(t["kind"], t["agent"], t["name"], t["reclaim_from"]) for t in led.turns] == list(TURNS)
        assert (len(led.tasks), len(led.decisions), len(led.handoffs)) == (12, 6, 4)
        assert sum(len(f["superseded"]) for f in led.facts) == 1
        assert [c["task_id"] for c in led.claims if c["reclaimed_from"]] == [sp.tid("t03-design-endpoints")]
        assert led.forgotten[0]["fact_labels"] == [f"database={sp.poison}"]
    # one clock for the whole history: sprint n+1 starts after sprint n ended
    ends = [led.marks["end"] for led in sl.ledgers]
    assert ends == sorted(ends) and len(set(ends)) == len(ends)


def test_every_op_has_an_answerer_and_scoped_ops_are_listed(truth):
    _, qs = truth
    ops = {
        n[4:]
        for n in vars(__import__("plexus.crucible.l2.plexus_answerer", fromlist=["x"]).PlexusAnswerer)
        if n.startswith("_op_")
    }
    sops = {n[5:] for n in vars(ScalePlexusAnswerer) if n.startswith("_sop_")}
    assert {q.op for q in qs} <= ops | sops
    assert sops == set(ScalePlexusAnswerer.SCOPED_OPS)


def test_conventions_and_cache_keys(truth):
    _, qs = truth
    q = qs[0]
    assert "sprints S01, S02" in CONVENTIONS_SCALE and CONVENTIONS_SCALE.rstrip().endswith(
        "in the format the question asks for."
    )
    base = cache_key("sonnet", "ctx", q)
    scaled = cache_key("sonnet", "ctx", q, conventions=CONVENTIONS_SCALE, version=SCALE_PROMPT_VERSION)
    assert base != scaled and SCALE_PROMPT_VERSION != PROMPT_VERSION


# ------------------------------------------------------------------------------------------------ retrieval
def test_tokenizer_keeps_identifiers_whole_and_in_parts():
    t = SC.tokens(
        "Which tasks does s07-t03-design-endpoints depend on? api_version=v13 0b7ef783-0955-57b2-a2ef-02e0d7570406"
    )
    assert "s07-t03-design-endpoints" in t and "s07" in t and "design" in t
    assert "api_version=v13" in t and "api_version" in t and "v13" in t
    assert "which" not in t and not any(x.startswith("0b7ef783") for x in t)


def test_bm25_ranks_the_matching_document_first():
    docs = ["alpha beta gamma", "s07 decision jwt tokens", "s08 decision jwt tokens", "unrelated words here"]
    bm = SC.Bm25(docs)
    assert bm.ranked("In sprint s07: which decision about jwt")[0] == 1
    assert bm.ranked("s08")[0] == 2
    assert bm.ranked("zzz")[0] == 0  # nothing matches: document order breaks the tie


@pytest.fixture(scope="module")
def small_history(tmp_path_factory):
    root = tmp_path_factory.mktemp("small")
    dirs = {}
    for arm in ("B0", "B1"):
        b = open_backend(BackendSpec(arm=arm, tenant="small", root=str(root), embedder="hash"))
        play_scale(b, 6)
        dirs[arm] = Path(b.dir)
        b.close()
    return dirs


def test_b0_selection_respects_the_budget_and_finds_the_sprint(small_history):
    q = "In sprint S05: Which tasks did the builder complete? s05-t06-write-db-schema"
    ctx = SC.b0_scale_context(small_history["B0"], q, budget=12_000)
    assert ctx.chars <= 12_000 and ctx.truncated and ctx.artifact_chars > 12_000
    assert "s05-t06-write-db-schema" in ctx.text and "=== file: tasks.json ===" in ctx.text
    share = SC.sprint_share(ctx, "s05")
    assert share["lines_with_sprint"] >= 5
    assert ctx.text == SC.b0_scale_context(small_history["B0"], q, budget=12_000).text  # deterministic


def test_b1_selection_always_has_the_schema_and_respects_the_budget(small_history):
    q = "In sprint S03: Which facts was the decision based on? S03: Use JWT bearer tokens"
    ctx = SC.b1_scale_context(small_history["B1"] / "crucible.db", q, budget=12_000)
    assert ctx.chars <= 12_000
    assert ctx.text.count("CREATE TABLE") == len(C.B1_TABLES)
    assert "S03: Use JWT bearer tokens" in ctx.text
    # the join table is searchable through the text of the decision and the fact it links
    assert "-- table decision_facts" in ctx.text


def test_evidence_diagnostic_is_a_word_check_not_a_score(truth):
    from plexus.crucible.l2.scale_run import evidence_in_context

    _, qs = truth
    q = next(x for x in qs if x.op == "value_history")
    assert evidence_in_context(q, "values v29 and v30") == {"found": 2, "total": 2}
    assert evidence_in_context(q, "nothing") == {"found": 0, "total": 2}
    yn = next(x for x in qs if x.kind == "yesno")
    assert evidence_in_context(yn, "x") is None


# ------------------------------------------------------------------------------------------------ the run
@pytest.fixture
def fake_answers(tmp_path, monkeypatch):
    qs = load_scale_questions(COMMITTED)
    ans = tmp_path / "answers.json"
    ans.write_text(
        json.dumps({q.id: (["nope"] if q.id == "Q14" else q.answer) for q in qs}), encoding="utf-8"
    )
    monkeypatch.setenv("FAKE_ANSWERS", str(ans))
    monkeypatch.setenv("FAKE_COUNT", str(tmp_path / "count.txt"))
    return tmp_path / "count.txt"


@pytest.mark.slow
def test_baselines_end_to_end_with_the_mocked_cli(tmp_path, fake_answers):
    doc, d = run_scale(
        mode="pilot", arms=("B0", "B1", "B2"), model="sonnet", budget_usd=5.0, host="127.0.0.1", port=DB_PORT,
        embedder="hash", out_root=tmp_path / "out", cache_dir=tmp_path / "cache", log=lambda s: None, launcher=FAKE,
        qpath=COMMITTED, run_id="t-pilot",
    )  # fmt: skip
    layer = doc["layers"]["L2_scale"]
    assert doc["run"]["layers"] == ["L2_scale"] and set(doc["layers"]) == {"L2_scale"}
    assert layer["question_set"]["ids"] == list(PILOT_IDS) and layer["question_set"]["total"] == 40
    h = layer["history"]
    assert (
        h["sprints"] == 20
        and h["artifact_chars_over_budget"]["B0"] >= 10
        and h["artifact_chars_over_budget"]["B1"] >= 10
    )
    for arm in ("B0", "B1", "B2"):
        a = layer["arms"][arm]
        assert {k: a["accuracy"][k] for k in ("correct", "total", "pct")} == {
            "correct": 4,
            "total": 5,
            "pct": 80.0,
        }
        assert a["accuracy"]["wilson95_pct"][0] < 80.0 < a["accuracy"]["wilson95_pct"][1]
        assert [r["id"] for r in a["questions"] if not r["correct"]] == ["Q14"]
        assert a["usage"]["llm_calls"] == 5 and a["usage"]["cost_usd"] == 0.05
        assert set(a["by_stratum"]) == {"early", "middle", "late"}
        assert a["context"]["chars_max"] <= 32_000
        assert all(r["context_chars"] <= 32_000 and r["sprint"].startswith("S") for r in a["questions"])
        assert a["failure_analysis"]["wrong"] == 1
        assert (d / "contexts" / arm / "Q03.txt").exists()
    assert len(fake_answers.read_text().split()) == 15  # 5 questions x 3 arms, all live
    # a second run is served from the cache: no new process
    run_scale(
        mode="pilot", arms=("B0", "B1", "B2"), model="sonnet", budget_usd=5.0, host="127.0.0.1", port=DB_PORT,
        embedder="hash", out_root=tmp_path / "out2", cache_dir=tmp_path / "cache", log=lambda s: None, launcher=FAKE,
        qpath=COMMITTED, run_id="t-pilot2",
    )  # fmt: skip
    assert len(fake_answers.read_text().split()) == 15
    from plexus.crucible.l2.scale_run import refresh_results

    refresh_results(
        d / "results.json", COMMITTED
    )  # no LLM: recomputes the diagnostic from the saved contexts
    assert "## Failure analysis" in (d / "report.md").read_text(encoding="utf-8")
    doc = json.loads((d / "results.json").read_text(encoding="utf-8"))
    report = render_scale_report(doc)
    for needle in (
        "## History vs the context budget",
        "## Failure analysis",
        "## Plexus changes",
        "## Honesty",
        "Q14",
    ):
        assert needle in report


@pytest.mark.integration
def test_plexus_answers_all_forty_match_ground_truth(opened):
    b = opened("P")
    sl = play_scale(b, K_SPRINTS)
    qs = build_scale_questions(sl)
    from plexus.graph.client import GraphClient

    client = GraphClient(host="127.0.0.1", port=DB_PORT)
    try:
        ans = ScalePlexusAnswerer(client, b.tenant)
        wrong = []
        for q in qs:
            got, meta = ans.answer(q)
            assert meta["statements"] >= 1
            ok, why = score(q, got)
            if not ok:
                wrong.append((q.id, q.op, q.answer, got, why))
        assert not wrong, wrong
    finally:
        client.close()


def test_question_roundtrip_through_yaml(tmp_path, truth):
    from plexus.crucible.l2.scale_questions import dump_scale_questions

    sl, qs = truth
    dump_scale_questions(qs, sl, tmp_path / "q.yaml")
    assert [q.to_json() for q in load_scale_questions(tmp_path / "q.yaml")] == [q.to_json() for q in qs]
    assert isinstance(qs[0], Question) and Sprint(3).tag == "S03"
