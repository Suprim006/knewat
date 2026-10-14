"""The claude -p runner (mocked CLI), the per-arm contexts and the end-to-end L2 run. No LLM is called."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from plexus.crucible.l2 import contexts as C
from plexus.crucible.l2.llm import BudgetExceeded, ClaudeRunner, cache_key, clean_env
from plexus.crucible.l2.questions import generate, score
from plexus.crucible.l2.scenario import play
from plexus.embed import HashEmbedder

FAKE = [sys.executable, str(Path(__file__).with_name("fake_claude_l2.py"))]
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def truth(tmp_path_factory):
    return generate(tmp_path_factory.mktemp("l2t"))


def runner(tmp_path, **kw):
    return ClaudeRunner("sonnet", cache_dir=tmp_path / "cache", launcher=FAKE, **kw)


@pytest.fixture
def fake_env(tmp_path, monkeypatch, truth):
    _, qs = truth
    ans = tmp_path / "answers.json"
    ans.write_text(json.dumps({q.id: q.answer for q in qs}), encoding="utf-8")
    monkeypatch.setenv("FAKE_ANSWERS", str(ans))
    monkeypatch.setenv("FAKE_COUNT", str(tmp_path / "count.txt"))
    return tmp_path / "count.txt"


def n_calls(p: Path) -> int:
    return len(p.read_text().splitlines()) if p.exists() else 0


def test_command_is_the_unmodified_cli_without_tools(tmp_path):
    cmd = ClaudeRunner("sonnet").command()
    joined = " ".join(cmd)
    assert cmd[1] == "-p" and "--model sonnet" in joined and "--max-turns 3" in joined
    assert "--tools " in joined and cmd[cmd.index("--tools") + 1] == ""
    assert "--strict-mcp-config" in cmd and "--output-format stream-json" in joined
    assert "--allowedTools" not in cmd and "--dangerously-skip-permissions" not in cmd


def test_api_key_is_removed_from_the_environment():
    assert "ANTHROPIC_API_KEY" not in clean_env({"ANTHROPIC_API_KEY": "x", "PATH": "p"})
    assert clean_env({"PATH": "p"})["PATH"] == "p"


def test_ask_scores_and_caches(tmp_path, truth, fake_env):
    _, qs = truth
    q, r = qs[4], runner(tmp_path)
    a = r.ask("B0", q, "context one")
    assert a.error == "" and a.parse_error == "" and not a.cached
    assert score(q, a.answer)[0]
    assert a.total_tokens > 0 and a.cost_usd == 0.01 and a.model == "claude-fake" and a.latency_ms > 0
    b = r.ask("B0", q, "context one")
    assert b.cached and b.answer == a.answer and b.cost_usd == a.cost_usd
    assert n_calls(fake_env) == 1
    r.ask("B0", q, "a different context")  # a different context is a different key
    assert n_calls(fake_env) == 2
    assert cache_key("sonnet", "x", q) != cache_key("haiku", "x", q)


@pytest.mark.parametrize(
    "mode,needle", [("deny", "permission_denials"), ("tool", "used tools"), ("fail", "no result")]
)
def test_protocol_violations_are_errors_not_answers(tmp_path, truth, fake_env, monkeypatch, mode, needle):
    monkeypatch.setenv("FAKE_MODE", mode)
    c = runner(tmp_path).ask("B1", truth[1][0], "ctx")
    assert needle in c.error
    assert not list((tmp_path / "cache").rglob("*.json"))  # errors are never cached


def test_garbage_reply_is_a_parse_error(tmp_path, truth, fake_env, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "garbage")
    c = runner(tmp_path).ask("B1", truth[1][0], "ctx")
    assert c.error == "" and c.answer is None and "not JSON" in c.parse_error


def test_budget_cap_stops_spending(tmp_path, truth, fake_env):
    _, qs = truth
    r = runner(tmp_path, budget_usd=0.015)
    r.ask("B0", qs[0], "c")
    r.ask("B0", qs[1], "c")
    with pytest.raises(BudgetExceeded):
        r.ask("B0", qs[2], "c")
    assert r.ask("B0", qs[0], "c").cached  # cached answers are free even after the cap


# ------------------------------------------------------------------------------------------------ contexts
def test_b0_context_has_every_file_and_fits(opened):
    b = opened("B0")
    play(b)
    ctx = C.b0_context(b.dir)
    assert not ctx.truncated and ctx.chars <= C.CONTEXT_CHARS
    for name in ("tasks.json", "MEMORY.md", "decisions.jsonl", "handoffs.jsonl", "logs/builder.jsonl"):
        assert f"=== file: {name} ===" in ctx.text
    assert "lock" not in " ".join(ctx.parts)


def test_budget_cut_is_reported(opened):
    b = opened("B0")
    play(b)
    ctx = C.b0_context(b.dir, budget=5000)
    assert ctx.truncated and ctx.chars <= 5000 and ctx.artifact_chars > 5000 and ctx.omitted


def test_b1_context_has_schema_and_rows(opened):
    b = opened("B1")
    play(b)
    ctx = C.b1_context(Path(b.path))
    assert "CREATE TABLE decisions(" in ctx.text and "decision_id,fact_id" in ctx.text
    assert "api_version" in ctx.text and "MongoDB 4" in ctx.text and not ctx.truncated
    assert (
        "norm_value"
        not in ctx.text.split("-- table facts")[1].split("-- table fact_agents")[0].splitlines()[2]
    )


def test_b2_retrieves_top_k_chunks(opened):
    b = opened("B2")
    play(b)
    idx = C.B2Index(Path(b.path), HashEmbedder())
    kinds = {k for k, _ in idx.chunks}
    assert kinds == {"fact", "decision", "handoff", "episode", "task", "source"}
    ctx = idx.context("Which facts was the decision about JWT bearer tokens based on?")
    assert ctx.text.count("\n[") == C.B2_TOP_K and ctx.chars < ctx.artifact_chars
    assert idx.top("same query") == idx.top("same query")  # deterministic


def test_two_plays_give_byte_identical_contexts(tmp_path):
    from plexus.crucible.api import BackendSpec
    from plexus.crucible.backends import open_backend

    seen = {}
    for run in ("a", "b"):
        for arm in ("B0", "B1"):
            b = open_backend(BackendSpec(arm=arm, tenant="det", root=str(tmp_path / run), embedder="hash"))
            play(b)
            b.close()
            ctx = C.b0_context(b.dir) if arm == "B0" else C.b1_context(Path(b.path))
            seen.setdefault(arm, set()).add(ctx.sha256)
    assert all(len(v) == 1 for v in seen.values()), seen
