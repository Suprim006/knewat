# ruff: noqa: E501  (long prose lines, as in mcp/ and cli.py)
"""``plexus code``: scan | baseline | hook-claude | hook-git | hook-run.

The client side of staleness (D-011). It runs on the developer machine, reads the repository, hashes files (and Python
functions / classes), and calls the ``mark_changed`` MCP tool of a Plexus server. It never needs the server's file
system, and ``hook-run`` never fails the edit that triggered it.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

from plexus.codescan import gitutil
from plexus.codescan.client import DEFAULT_AGENT, McpCallError, Session, default_url, run_session
from plexus.codescan.fastclient import FastSession, run_fast_session
from plexus.codescan.paths import absolute_canonical
from plexus.codescan.workflow import (
    Summary,
    commit_groups,
    describe_suspects,
    fact_line,
    format_report,
    send,
    tracked_files,
    working_groups,
)

HOOK_TOOLS = ("Edit", "Write", "MultiEdit")
HOOK_TIMEOUT_S = 5.0
MARK_BEGIN = "# >>> plexus staleness hook (plexus code hook-git) >>>"
MARK_END = "# <<< plexus staleness hook <<<"
DOCS = "https://code.claude.com/docs/en/hooks (PostToolUse input, and hookSpecificOutput.additionalContext)"


def _python_command() -> str:
    """Runs the ``plexus code`` group of this checkout without the rest of the CLI (fast start)."""
    return f'"{sys.executable.replace(chr(92), "/")}" -m plexus.codescan'


def _sub(command: str | None, name: str) -> str:
    """``<command> code <name>`` for a user-given command (e.g. ``plexus``), else the module form."""
    return f"{command} code {name}" if command else f"{_python_command()} {name}"


def _tenant(a: argparse.Namespace) -> str:
    t = a.tenant or os.environ.get("PLEXUS_TENANT")
    if not t:
        raise SystemExit("--tenant is required (or set PLEXUS_TENANT)")
    return t


# ------------------------------------------------------------------------------------------------ scan
def cmd_scan(a: argparse.Namespace) -> int:
    repo = str(Path(a.repo or os.getcwd()).resolve())
    tenant = _tenant(a)
    try:
        if a.paths:
            commit, at, groups = a.commit or "", None, working_groups(repo, a.paths)
        else:
            commit, at, groups = commit_groups(repo, a.commit or "HEAD")
        if not groups:
            print("plexus code scan: no changed files")
            return 0

        async def go(s: Session):
            summary = await send(s, groups, commit=commit, at=at)
            return summary, await describe_suspects(s, summary)

        summary, rows = run_session(a.url, tenant, a.agent, go, timeout=a.timeout)
    except (McpCallError, gitutil.GitError, ValueError) as exc:
        print(f"plexus code scan: {exc}", file=sys.stderr)
        return 1
    print(format_report(f"plexus code scan {commit[:10] or 'working tree'}", summary, rows))
    return 0


# ------------------------------------------------------------------------------------------------ baseline
def cmd_baseline(a: argparse.Namespace) -> int:
    repo = str(Path(a.repo or os.getcwd()).resolve())
    tenant = _tenant(a)
    try:
        paths = list(a.paths or [])
        if not paths:
            try:
                paths = tracked_files(repo, tenant)
            except Exception as exc:  # FalkorDB not reachable from here
                print(
                    f"plexus code baseline: cannot list the tracked files from the database ({type(exc).__name__}); "
                    "pass --paths, or set FALKORDB_HOST / FALKORDB_PORT",
                    file=sys.stderr,
                )
                return 1
        if not paths:
            print("plexus code baseline: the graph tracks no file of this repository (nothing to do)")
            return 0
        groups = working_groups(repo, paths, baseline=True)

        async def go(s: Session) -> Summary:
            return await send(s, groups)

        summary = run_session(a.url, tenant, a.agent, go, timeout=a.timeout)
    except (McpCallError, gitutil.GitError, ValueError) as exc:
        print(f"plexus code baseline: {exc}", file=sys.stderr)
        return 1
    print(
        f"plexus code baseline: {len(paths)} files, {summary.entries} entries sent in {summary.calls} call(s); "
        f"{summary.changed} differed from what the graph already knew, "
        f"{len(summary.suspect_fact_ids)} memories made suspect"
    )
    return 0


# ------------------------------------------------------------------------------------------------ hooks
def hook_settings(tenant: str, url: str, command: str | None = None) -> dict[str, Any]:
    """The Claude Code settings fragment that runs ``code hook-run`` after every Edit / Write / MultiEdit."""
    cmd = f"{_sub(command, 'hook-run')} --tenant {shlex.quote(tenant)} --url {shlex.quote(url)}"
    return {
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "|".join(HOOK_TOOLS),
                    "hooks": [{"type": "command", "command": cmd, "timeout": 10}],
                }
            ]
        }
    }


def cmd_hook_claude(a: argparse.Namespace) -> int:
    print(json.dumps(hook_settings(_tenant(a), a.url, a.command), indent=2))
    print(
        "// merge into .claude/settings.json (project) or ~/.claude/settings.json; schema: " + DOCS,
        file=sys.stderr,
    )
    return 0


def git_hook_block(repo: str, tenant: str, url: str, command: str | None = None) -> str:
    line = (
        f'{_sub(command, "scan")} --repo "{repo.replace(chr(92), "/")}" '
        f"--tenant {shlex.quote(tenant)} --url {shlex.quote(url)} --commit HEAD || true"
    )
    return f"{MARK_BEGIN}\n{line}\n{MARK_END}\n"


def cmd_hook_git(a: argparse.Namespace) -> int:
    repo = gitutil.toplevel(a.repo or os.getcwd())
    if not repo:
        print("plexus code hook-git: not inside a git work tree", file=sys.stderr)
        return 1
    hooks = Path(gitutil.run_git(repo, "rev-parse", "--git-path", "hooks").decode().strip())
    if not hooks.is_absolute():
        hooks = Path(repo) / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    target = hooks / "post-commit"
    block = git_hook_block(repo, _tenant(a), a.url, a.command)
    text = target.read_text(encoding="utf-8") if target.exists() else "#!/bin/sh\n"
    if MARK_BEGIN in text:  # replace our own earlier block
        head, _, rest = text.partition(MARK_BEGIN)
        _, _, tail = rest.partition(MARK_END + "\n")
        text = head + block + tail
    else:
        text = text.rstrip("\n") + "\n" + block
    target.write_text(text, encoding="utf-8", newline="\n")
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"wrote {target}")
    return 0


def hook_message(file_path: str, summary: Summary, rows: list[dict[str, Any]]) -> str:
    name = Path(file_path).name
    n = len(summary.suspect_fact_ids)
    shown = "; ".join(fact_line(r)[:120] for r in rows[:3])
    more = f" (+{n - len(rows[:3])} more)" if n > len(rows[:3]) else ""
    msg = f"Plexus: {n} {'memory' if n == 1 else 'memories'} about {name} may be stale: {shown}{more}."
    if summary.decisions_total:
        msg += f" {summary.decisions_total} decision(s) rest on them."
    if summary.docs:
        msg += (
            " Docs that describe it: "
            + ", ".join(sorted({Path(d["uri"]).name for d in summary.docs.values()})[:3])
            + "."
        )
    return msg + " Re-check what you rely on: call facts_to_verify, then verify_fact."


def cmd_hook_run(a: argparse.Namespace) -> int:
    """Claude Code ``PostToolUse`` hook. Reads the event from stdin; ALWAYS exits 0 (never fails the edit)."""
    try:
        data = json.loads(sys.stdin.read() or "{}")
        tool_input = data.get("tool_input") or {}
        file_path = tool_input.get("file_path") or tool_input.get("path")
        if data.get("tool_name") not in HOOK_TOOLS or not file_path:
            return 0
        cwd = data.get("cwd") or os.getcwd()
        groups = working_groups(cwd, [file_path])
        tenant = _tenant(a)

        async def go(s: FastSession):
            summary = await send(s, groups)  # type: ignore[arg-type]
            return summary, await describe_suspects(s, summary)  # type: ignore[arg-type]

        summary, rows = run_fast_session(a.url, tenant, a.agent, go, timeout=min(a.timeout, HOOK_TIMEOUT_S))
        if summary.suspect_fact_ids:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PostToolUse",
                            "additionalContext": hook_message(
                                absolute_canonical(file_path, cwd), summary, rows
                            ),
                        }
                    }
                )
            )
    except SystemExit as exc:  # a missing --tenant must not fail the edit either
        print(f"plexus hook-run: {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"plexus hook-run: {type(exc).__name__}: {str(exc)[:200]}", file=sys.stderr)
    return 0


# ------------------------------------------------------------------------------------------------ parser
def add_code_commands(sub: Any) -> None:
    """Register the ``code`` group on the main parser's sub-parsers."""
    code = sub.add_parser("code", help="staleness: tell Plexus which memories a code change makes suspect")
    cs = code.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser, timeout: float = 10.0) -> None:
        sp.add_argument("--tenant", help="tenant (default: env PLEXUS_TENANT)")
        sp.add_argument(
            "--url", default=default_url(), help="Plexus MCP base URL (default env PLEXUS_URL or :8765)"
        )
        sp.add_argument(
            "--agent", default=DEFAULT_AGENT, help=f"agent id used for the calls (default {DEFAULT_AGENT})"
        )
        sp.add_argument("--timeout", type=float, default=timeout, help="seconds to wait for the server")

    s = cs.add_parser("scan", help="report the files a commit (default HEAD) or --paths changed")
    s.add_argument("--repo", help="repository directory (default: current directory)")
    s.add_argument("--commit", help="commit to scan (default HEAD); with --paths it only labels the change")
    s.add_argument("--paths", nargs="+", help="scan these files as they are on disk instead of a commit")
    common(s)
    s.set_defaults(fn=cmd_scan)

    s = cs.add_parser(
        "baseline", help="record the current hashes of tracked files; marks nothing new as stale"
    )
    s.add_argument("--repo", help="repository directory (default: current directory)")
    s.add_argument(
        "--paths",
        nargs="+",
        help="files to record (default: the files of this repo that have a Source or anchor in the graph, "
        "read from FalkorDB via FALKORDB_HOST/PORT)",
    )
    common(s, 60.0)
    s.set_defaults(fn=cmd_baseline)

    s = cs.add_parser("hook-claude", help="print the Claude Code settings.json fragment (PostToolUse hook)")
    s.add_argument("--command", help="command that runs plexus (default: this Python with -m plexus.cli)")
    common(s)
    s.set_defaults(fn=cmd_hook_claude)

    s = cs.add_parser("hook-git", help="install .git/hooks/post-commit that runs 'code scan --commit HEAD'")
    s.add_argument("--repo", help="repository directory (default: current directory)")
    s.add_argument("--command", help="command that runs plexus (default: this Python with -m plexus.cli)")
    common(s)
    s.set_defaults(fn=cmd_hook_git)

    s = cs.add_parser(
        "hook-run", help="(called by Claude Code) read a PostToolUse event on stdin; never fails"
    )
    common(s, HOOK_TIMEOUT_S)
    s.set_defaults(fn=cmd_hook_run)
