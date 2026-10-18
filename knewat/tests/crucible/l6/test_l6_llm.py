"""The L6 LLM arms with a fake ``claude``: command lines, cache, caps, tool policy, reply parsing, the SQL tool and a toy pilot."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

from plexus.crucible.l2.llm import BudgetExceeded
from plexus.crucible.l6 import llm as L
from plexus.crucible.l6 import pilot as P
from plexus.crucible.l6 import sql_mcp

FAKE = [sys.executable, str(Path(__file__).with_name("fake_claude_l6.py"))]


def runner(tmp_path: Path, **kw) -> L.PilotRunner:
    return L.PilotRunner(tmp_path / "cache", launcher=FAKE, **kw)


def ask(r: L.PilotRunner, arm: str = "B0r", qid: str = "A01", **kw) -> L.Call:
    return r.ask(
        arm,
        "A",
        qid,
        f"Question {qid}: how many?\nAnswer format: x\n",
        data_sha="abc",
        db="x.db",
        files_dir=Path("."),
        **kw,
    )


def test_commands_per_arm_never_bare_and_tools_are_exact(tmp_path):
    r = runner(tmp_path)
    for arm in L.ROLES:
        if arm == "P":
            continue
        cmd = r.command(arm, tmp_path / "m.json")
        assert "--bare" not in cmd and "--no-session-persistence" in cmd and "--disable-slash-commands" in cmd
        assert cmd[cmd.index("--max-turns") + 1] == str(L.MAX_TURNS[arm])
        assert cmd[cmd.index("--max-budget-usd") + 1] == "0.8"
    assert r.command("B0r", None)[r.command("B0r", None).index("--tools") + 1] == ""
    b1a = r.command("B1a", tmp_path / "m.json")
    assert (
        b1a[b1a.index("--allowedTools") + 1] == "mcp__sql__query"
        and "--mcp-config" in b1a
        and b1a[b1a.index("--tools") + 1] == ""
    )
    b0g = r.command("B0g", None)
    assert b0g[b0g.index("--tools") + 1] == "Bash,Read,Grep,Glob" and "--mcp-config" not in b0g


def test_cache_hit_costs_nothing_and_reparses(tmp_path, monkeypatch):
    count = tmp_path / "count"
    monkeypatch.setenv("FAKE_COUNT", str(count))
    ans = tmp_path / "a.json"
    ans.write_text(json.dumps({"A01": {"facts": 3}}))
    monkeypatch.setenv("FAKE_ANSWERS", str(ans))
    monkeypatch.setenv("FAKE_PROSE", "1")
    r = runner(tmp_path)
    c1 = ask(r)
    assert c1.answer == {"facts": 3} and not c1.cached and c1.cost_usd == 0.05
    c2 = ask(r)
    assert c2.cached and c2.answer == {"facts": 3} and len(count.read_text().splitlines()) == 1
    assert r.spent == pytest.approx(0.05)
    # a different data hash is a different key
    r.ask("B0r", "A", "A01", "Question A01: how many?\nAnswer format: x\n", data_sha="other")
    assert len(count.read_text().splitlines()) == 2


def test_caps_are_cumulative_and_per_arm(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_COST", "0.40")
    r = runner(tmp_path, total_cap=0.7, arm_caps={"B0r": 0.5})
    ask(r, qid="A01")
    ask(r, qid="A02")  # 0.4 < 0.5: allowed, now 0.8 spent
    with pytest.raises(BudgetExceeded):
        ask(r, qid="A03")
    r2 = runner(tmp_path, total_cap=1.0)  # a new process counts what the cache already holds
    assert r2.spent == pytest.approx(0.8) and r2.arm_spent["B0r"] == pytest.approx(0.8)
    ask(r2, qid="A03")
    with pytest.raises(BudgetExceeded):
        ask(r2, qid="A04")


def test_tool_policy(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_TOOLS", "Bash")
    r = runner(tmp_path)
    assert "disallowed tool use" in ask(r, "B0r", "A01").error  # the reader has no tools
    assert not ask(r, "B0g", "A02").error  # Bash is allowed for the files agent
    assert "disallowed tool use" in ask(r, "B1a", "A03").error  # the SQL agent has only mcp__sql__query


def test_max_turns_is_a_wrong_answer_not_a_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SUBTYPE", "error_max_turns")
    r = runner(tmp_path)
    c = ask(r, "B1a", "A01")
    assert c.error == "max_turns" and c.cost_usd == 0.05
    again = ask(r, "B1a", "A01")
    assert again.cached and again.error == "max_turns"  # not re-run, not re-paid


def test_sql_tool_is_read_only_and_bounded(tmp_path):
    db = tmp_path / "t.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE t(a INTEGER)")
    c.executemany("INSERT INTO t VALUES(?)", [(i,) for i in range(500)])
    c.commit()
    c.close()
    ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    box = [0.0]
    assert sql_mcp.run_query(ro, "SELECT count(*) AS n FROM t", box).splitlines() == ["n", "500"]
    out = sql_mcp.run_query(ro, "SELECT a FROM t", box)
    assert len(out.splitlines()) == 202 and "cut" in out.splitlines()[-1]
    for bad in (
        "DELETE FROM t",
        "DROP TABLE t",
        "SELECT 1; DELETE FROM t",
        "PRAGMA writable_schema=1",
        "INSERT INTO t VALUES(1)",
    ):
        with pytest.raises(Exception, match="only SELECT|one statement"):
            sql_mcp.run_query(ro, bad, box)
    assert sqlite3.connect(db).execute("SELECT count(*) FROM t").fetchone()[0] == 500


def test_prep_context_obeys_the_cap_and_prefers_relevant_lines(tmp_path):
    prep = P.Prep("A", tmp_path, scale=0.05)
    q = prep.qs[3]
    ctx = prep.context(q)
    assert len(ctx) <= P.CONTEXT_CHARS
    assert q.source in ctx or q.probes[0] in ctx
    assert prep.prompt(q).startswith("Question A04:")
    assert "BASED_ON" not in prep.prompt(q)  # no Cypher-ish leakage of internals into the question


def test_toy_pilot_end_to_end_with_the_fake(tmp_path, monkeypatch):
    # every question answered "unknown": all wrong, but the machinery (rows, costs, caps, files) is exercised
    monkeypatch.setenv("FAKE_COST", "0.02")
    doc = P.run_pilot(
        "all", tmp_path / "out", 0.05, FAKE, log=lambda s: None, cache=tmp_path / "cache", graphs=False
    )
    assert doc["kind"] == "pilot" and not doc["partial"]
    assert set(doc["families"]) == {"A", "B", "D"}
    for fam, f in doc["families"].items():
        assert set(f["arms"]) == {a for a in P.ARMS if a != "P" or fam in P.P_FAMILIES}, fam
        for a in f["arms"].values():
            assert (
                a["n"] == len(f["pilot_ids"])
                and a["strict_correct"] == 0
                and a["cost_usd"] == pytest.approx(0.02 * a["n"])
            )
    assert doc["run"]["cost_usd"] == pytest.approx(0.02 * doc["run"]["llm_calls"])
    assert (tmp_path / "out" / "latest-pilot.json").exists()
    # second run: everything cached, nothing live
    doc2 = P.run_pilot(
        "all", tmp_path / "out2", 0.05, FAKE, log=lambda s: None, cache=tmp_path / "cache", graphs=False
    )
    assert doc2["run"]["calls_run_live"] == 0 and doc2["run"]["cost_live_usd"] == 0


def test_parse_reply_accepts_the_bare_object_of_the_format_and_nothing_else():
    assert L.parse_reply('Reasoning.\n{"answer": 5}') == (5, "")
    assert L.parse_reply('Reasoning.\n```json\n{"chain": ["f1"], "agent": "a1"}\n```') == (
        {"chain": ["f1"], "agent": "a1"},
        "",
    )
    assert L.parse_reply('So: {"x": 1}\n{"chain": ["f1"], "agent": "a1"}') == (
        {"chain": ["f1"], "agent": "a1"},
        "",
    )
    assert L.parse_reply('{"chain": ["f1"]} and that is all')[0] is None  # text after the object
    assert L.parse_reply("no json at all")[0] is None
    assert L.parse_reply('{"answer": 1, "why": "x"}') == ({"answer": 1, "why": "x"}, "")
