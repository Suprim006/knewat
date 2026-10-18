"""``knewat code hook-run`` (Claude Code PostToolUse), ``hook-claude`` and ``hook-git``."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import time

import pytest

from knewat.cli import build_parser
from knewat.codescan.cli import MARK_BEGIN, hook_settings
from knewat.codescan.client import McpCallError, run_session
from knewat.codescan.fastclient import run_fast_session
from knewat.codescan.paths import canonical_path

from .conftest import commit_all

V1 = "def pay(x):\n    return x\n\n\ndef refund(x):\n    return -x\n"
V2 = V1.replace("return x\n\n\ndef refund", "return x + 1\n\n\ndef refund")


def run(argv: list[str]) -> int:
    a = build_parser().parse_args(argv)
    return a.fn(a)


def event(path, tool="Edit", cwd=None, **extra) -> str:
    return json.dumps(
        {
            "session_id": "s1",
            "cwd": str(cwd or ""),
            "hook_event_name": "PostToolUse",
            "tool_name": tool,
            "tool_input": {"file_path": str(path), "old_string": "a", "new_string": "b"},
            "tool_response": {"filePath": str(path), "success": True},
            "tool_use_id": "toolu_1",
            **extra,
        }
    )


def hook(monkeypatch, capsys, stdin: str, *args: str) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    code = run(["code", "hook-run", *args])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


@pytest.fixture
def project(live, repo):
    (repo / "pay.py").write_text(V1, encoding="utf-8", newline="\n")
    commit_all(repo, "init")
    py = canonical_path(str(repo / "pay.py"))

    async def setup(s):
        f1 = (await s.call("assert_fact", subject="pay", predicate="behaviour", value="returns x"))["fact_id"]
        f2 = (await s.call("assert_fact", subject="refund", predicate="behaviour", value="negates"))[
            "fact_id"
        ]
        await s.call("anchor_fact", fact_id=f1, path=py, symbol="pay")
        await s.call("anchor_fact", fact_id=f2, path=py, symbol="refund")
        return f1, f2

    f1, f2 = run_session(live.url, live.tenant, "alice", setup)
    args = ["--tenant", live.tenant, "--url", live.url]
    code = run(["code", "baseline", "--repo", str(repo), *args, "--paths", "pay.py"])
    assert code == 0
    return {"repo": repo, "py": py, "f1": f1, "f2": f2, "args": args}


def test_an_edit_that_makes_memories_suspect_returns_additional_context(live, project, monkeypatch, capsys):
    repo = project["repo"]
    (repo / "pay.py").write_text(V2, encoding="utf-8", newline="\n")
    capsys.readouterr()
    code, out, err = hook(monkeypatch, capsys, event(repo / "pay.py", cwd=repo), *project["args"])
    assert code == 0 and err == ""
    msg = json.loads(out)  # exactly one JSON object on stdout
    assert set(msg) == {"hookSpecificOutput"}
    h = msg["hookSpecificOutput"]
    assert h["hookEventName"] == "PostToolUse"
    assert "1 memory about pay.py may be stale" in h["additionalContext"]
    assert (
        "pay behaviour: returns x" in h["additionalContext"] and "facts_to_verify" in h["additionalContext"]
    )
    states = dict(live.rows("MATCH (f:Fact) RETURN f.id, coalesce(f.verify_state,'verified')"))
    assert states[project["f1"]] == "suspect" and states[project["f2"]] == "verified"


def test_an_edit_that_changes_nothing_prints_nothing(project, monkeypatch, capsys):
    repo = project["repo"]
    capsys.readouterr()
    code, out, err = hook(monkeypatch, capsys, event(repo / "pay.py", cwd=repo), *project["args"])
    assert (code, out, err) == (0, "", "")


def test_write_and_multiedit_and_windows_style_paths_are_handled(project, monkeypatch, capsys):
    repo = project["repo"]
    (repo / "pay.py").write_text(V2, encoding="utf-8", newline="\n")
    capsys.readouterr()
    win = str(repo / "pay.py").replace("/", "\\")
    code, out, _ = hook(monkeypatch, capsys, event(win, tool="MultiEdit", cwd=repo), *project["args"])
    assert code == 0 and "may be stale" in out


@pytest.mark.parametrize("tool", ["Read", "Bash", "Grep", ""])
def test_other_tools_are_ignored_without_touching_the_server(tool, monkeypatch, capsys):
    code, out, err = hook(
        monkeypatch, capsys, event("C:/x/y.py", tool=tool), "--tenant", "t", "--url", "http://127.0.0.1:9"
    )
    assert (code, out, err) == (0, "", "")


@pytest.mark.parametrize("stdin", ["", "not json", "[]", "{}", '{"tool_name": "Edit"}', "null"])
def test_garbage_on_stdin_never_fails(stdin, monkeypatch, capsys):
    code, out, _ = hook(monkeypatch, capsys, stdin, "--tenant", "t", "--url", "http://127.0.0.1:9")
    assert code == 0 and out == ""


def test_an_unreachable_server_exits_zero_quickly_with_a_one_line_note(tmp_path, monkeypatch, capsys):
    f = tmp_path / "a.py"
    f.write_text("x = 1\n")
    t0 = time.monotonic()
    code, out, err = hook(
        monkeypatch, capsys, event(f, cwd=tmp_path), "--tenant", "t", "--url", "http://127.0.0.1:9"
    )
    assert code == 0 and out == "" and time.monotonic() - t0 < 5.5
    assert err.startswith("knewat hook-run:") and err.count("\n") == 1


def test_a_missing_tenant_does_not_fail_the_edit(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("KNEWAT_TENANT", raising=False)
    code, out, err = hook(monkeypatch, capsys, event(tmp_path / "a.py", cwd=tmp_path))
    assert code == 0 and out == "" and "tenant" in err


def test_hook_run_is_a_real_subprocess_that_exits_zero(live, project, tmp_path):
    repo = project["repo"]
    (repo / "pay.py").write_text(V2, encoding="utf-8", newline="\n")
    t0 = time.monotonic()
    p = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "knewat.codescan", "hook-run", *project["args"]],
        input=event(repo / "pay.py", cwd=repo),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert p.returncode == 0, p.stderr
    assert "additionalContext" in json.loads(p.stdout)["hookSpecificOutput"]
    assert (
        time.monotonic() - t0 < 4
    )  # the budget is 2 s typical (measured in docs/staleness.md); loose bound for CI


# -- installers -------------------------------------------------------------------------------------------
def test_hook_claude_prints_a_posttooluse_fragment(capsys):
    assert run(["code", "hook-claude", "--tenant", "acme", "--url", "http://127.0.0.1:8765"]) == 0
    cfg = json.loads(capsys.readouterr().out)
    (entry,) = cfg["hooks"]["PostToolUse"]
    assert entry["matcher"] == "Edit|Write|MultiEdit"
    (h,) = entry["hooks"]
    assert h["type"] == "command" and h["timeout"] == 10
    assert "-m knewat.codescan hook-run --tenant acme --url http://127.0.0.1:8765" in h["command"]
    assert hook_settings("t", "u", "knewat")["hooks"]["PostToolUse"][0]["hooks"][0]["command"].startswith(
        "knewat code"
    )


def test_hook_git_installs_an_executable_idempotent_post_commit(repo, capsys):
    args = ["code", "hook-git", "--repo", str(repo), "--tenant", "acme", "--url", "http://127.0.0.1:8765"]
    assert run(args) == 0
    hook_file = repo / ".git" / "hooks" / "post-commit"
    text = hook_file.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\n") and text.count(MARK_BEGIN) == 1
    assert (
        "-m knewat.codescan scan --repo" in text
        and "--commit HEAD || true" in text
        and "--tenant acme" in text
    )
    assert "\r" not in text
    run(args)
    run(args)
    assert hook_file.read_text(encoding="utf-8") == text  # replaced, not appended


def test_hook_git_keeps_an_existing_hook(repo):
    hooks = repo / ".git" / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / "post-commit").write_text("#!/bin/sh\necho mine\n", encoding="utf-8", newline="\n")
    assert run(["code", "hook-git", "--repo", str(repo), "--tenant", "acme"]) == 0
    text = (hooks / "post-commit").read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh\necho mine\n") and MARK_BEGIN in text


def test_the_installed_git_hook_runs_on_commit(live, repo, capsys):
    (repo / "pay.py").write_text(V1, encoding="utf-8", newline="\n")
    commit_all(repo, "init")
    py = canonical_path(str(repo / "pay.py"))

    async def setup(s):
        f = (await s.call("assert_fact", subject="pay", predicate="behaviour", value="returns x"))["fact_id"]
        await s.call("anchor_fact", fact_id=f, path=py, symbol="pay")
        return f

    f = run_session(live.url, live.tenant, "alice", setup)
    base = ["--tenant", live.tenant, "--url", live.url]
    assert run(["code", "baseline", "--repo", str(repo), *base, "--paths", "pay.py"]) == 0
    assert run(["code", "hook-git", "--repo", str(repo), *base]) == 0
    time.sleep(1.1)
    (repo / "pay.py").write_text(V2, encoding="utf-8", newline="\n")
    commit_all(repo, "edit pay")  # post-commit runs `knewat code scan --commit HEAD`
    state = live.rows("MATCH (f:Fact {id:$f}) RETURN f.verify_state", f=f)
    assert state == [["suspect"]]
    assert live.rows("MATCH (c:Change) RETURN count(c)") == [[1]]


def test_the_fast_client_speaks_the_same_protocol_and_reports_tool_errors(live):
    async def ok(s):
        a = await s.call("add_source", title="doc", uri="C:/x/doc.md")
        b = await s.call("add_source", title="doc", uri="C:/x/doc.md")
        return a["source_id"], b["source_id"]

    a, b = run_fast_session(live.url, live.tenant, "alice", ok)
    assert a == b  # same uri, same source; the session survived two calls
    assert live.rows("MATCH (t:ToolCall {tool:'add_source'}) RETURN count(t)") == [[2]]

    async def bad(s):
        return await s.call("anchor_fact", fact_id="nope", path="C:/x.py")

    with pytest.raises(McpCallError, match="nope"):
        run_fast_session(live.url, live.tenant, "alice", bad)
    with pytest.raises(McpCallError, match="cannot reach"):
        run_fast_session("http://127.0.0.1:9", "t", "a", bad, timeout=2)
    with pytest.raises(McpCallError, match="bad Knewat url"):
        run_fast_session("ftp://x", "t", "a", bad)
