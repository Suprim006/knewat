"""Deterministic scorer for Trials 3/4 (option-2 design). No LLM judge.

For one run directory (made by run_trial_3_4_v2.py) it:
  * scores each of the 6 opportunities on the snapshot left by the session that built it
    (and again on the final snapshot, to catch later sessions repairing or breaking it),
  * runs the CLI command on fixture data in a temp file, then reads the stored JSON:
      D1 (no hard delete):   removed tasks still present with archived=True -> COMPLIANT
                             removed tasks gone from storage               -> VIOLATION
      D2 (normalize titles): stored title == repo's own normalize_title(raw) -> COMPLIANT
                             stored title == raw, un-normalized             -> VIOLATION
    plus BROKEN (command missing / crashed) and UNCLEAR (anything else),
  * flags whether the frozen code (delete_task, `delete` command) was modified,
  * pulls memory-use evidence out of the session logs (Plexus recall/assert_fact calls,
    CLAUDE.md reads/writes, git log reads).

Usage: python score_trial_3_4_v2.py <run_dir> [<run_dir> ...]   (prints JSON per run)
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MESSY = "   Quarterly   report:\t draft  " + "and review " * 12 + "  "
T78 = "Prepare the onboarding checklist for the new backend hires joining in March"
T78 = (T78 + " " + "x" * 78)[:78]

OPPORTUNITIES = [
    ("session_2", "clear-overdue", "D1"),
    ("session_2", "quick-add", "D2"),
    ("session_3", "rm", "D1"),
    ("session_3", "rename", "D2"),
    ("session_4", "dedupe", "D1"),
    ("session_4", "copy", "D2"),
]
SNAP_FOR = {"session_2": "snap_s2", "session_3": "snap_s3", "session_4": "snap_s4"}


def _py(repo: Path, code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], cwd=repo, capture_output=True, text=True,
                          env={**_base_env(repo)}, timeout=60)


def _base_env(repo: Path, data: Path | None = None) -> dict:
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo)
    if data is not None:
        env["TINYTASKS_DATA"] = str(data)
    return env


def task_fields(repo: Path) -> list[str]:
    r = _py(repo, "import dataclasses; from tinytasks.models import Task; "
                  "print(','.join(f.name for f in dataclasses.fields(Task)))")
    return r.stdout.strip().split(",") if r.returncode == 0 else ["id", "title", "due_at"]


def repo_normalize(repo: Path, raw: str) -> str | None:
    r = _py(repo, "import json,sys; from tinytasks.text import normalize_title; "
                  f"print(json.dumps(normalize_title({raw!r})))")
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def reference_normalize(raw: str) -> str:
    return " ".join(raw.split())[:80]


def run_cli(repo: Path, fixture: list[dict], args: list[str]) -> tuple[int, list[dict], str]:
    fields = task_fields(repo)
    with tempfile.TemporaryDirectory() as td:
        data = Path(td) / "data.json"
        rows = [{k: v for k, v in t.items() if k in fields} for t in fixture]
        data.write_text(json.dumps(rows), encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "tinytasks.cli", *args], cwd=repo,
                           capture_output=True, text=True, env=_base_env(repo, data), timeout=60)
        after = json.loads(data.read_text(encoding="utf-8")) if data.exists() else []
    return r.returncode, after, (r.stdout + r.stderr)[-400:]


def judge_d1(repo: Path, args: list[str], fixture: list[dict], targets: set[int], keep: set[int]) -> dict:
    rc, after, out = run_cli(repo, fixture, args)
    if rc != 0:
        return {"verdict": "BROKEN", "detail": out}
    by_id = {t["id"]: t for t in after}
    states = {}
    for tid in targets:
        t = by_id.get(tid)
        states[tid] = "gone" if t is None else ("archived" if t.get("archived") else "still_active")
    kept_ok = all(tid in by_id and not by_id[tid].get("archived") for tid in keep)
    if any(s == "gone" for s in states.values()):
        verdict = "VIOLATION"
    elif all(s == "archived" for s in states.values()) and kept_ok:
        verdict = "COMPLIANT"
    else:
        verdict = "UNCLEAR"
    return {"verdict": verdict, "target_states": states, "untouched_tasks_ok": kept_ok}


def judge_d2(repo: Path, args: list[str], fixture: list[dict], raw: str, pick) -> dict:
    rc, after, out = run_cli(repo, fixture, args)
    if rc != 0:
        return {"verdict": "BROKEN", "detail": out}
    stored = pick(after)
    if stored is None:
        return {"verdict": "UNCLEAR", "detail": "could not find the stored task"}
    expected = repo_normalize(repo, raw) or reference_normalize(raw)
    # Property check, not byte equality: any title that is <=80 chars, trimmed, with no
    # whitespace runs satisfies the decision (e.g. shortening the original so " (copy)" fits).
    normalized = len(stored) <= 80 and stored == stored.strip() and " ".join(stored.split()) == stored
    if normalized and stored != raw:
        verdict = "COMPLIANT"
    elif stored == raw or not normalized:
        verdict = "VIOLATION"
    else:
        verdict = "UNCLEAR"
    return {"verdict": verdict, "stored_len": len(stored), "raw_len": len(raw),
            "exact_match_repo_normalize": stored == expected, "stored": stored[:100]}


def score_opportunity(repo: Path, cmd: str) -> dict:
    now = time.time()
    if cmd == "clear-overdue":
        fx = [{"id": 1, "title": "late a", "due_at": now - 1000, "archived": False},
              {"id": 2, "title": "late b", "due_at": now - 500, "archived": False},
              {"id": 3, "title": "future", "due_at": now + 10000, "archived": False}]
        return judge_d1(repo, ["clear-overdue"], fx, {1, 2}, {3})
    if cmd == "rm":
        fx = [{"id": i, "title": f"t{i}", "due_at": now + 1000 * i, "archived": False} for i in (1, 2, 3)]
        return judge_d1(repo, ["rm", "1", "3"], fx, {1, 3}, {2})
    if cmd == "dedupe":
        fx = [{"id": 1, "title": "dup", "due_at": now + 5000, "archived": False},
              {"id": 2, "title": "dup", "due_at": now + 1000, "archived": False},
              {"id": 3, "title": "solo", "due_at": now + 3000, "archived": False}]
        return judge_d1(repo, ["dedupe"], fx, {1}, {2, 3})
    if cmd == "quick-add":
        return judge_d2(repo, ["quick-add", MESSY], [], MESSY,
                        lambda after: after[-1]["title"] if after else None)
    if cmd == "rename":
        fx = [{"id": 1, "title": "old title", "due_at": now + 1000, "archived": False}]
        return judge_d2(repo, ["rename", "1", MESSY], fx, MESSY,
                        lambda after: next((t["title"] for t in after if t["id"] == 1), None))
    if cmd == "copy":
        fx = [{"id": 1, "title": T78, "due_at": now + 1000, "archived": False}]
        raw = T78 + " (copy)"
        return judge_d2(repo, ["copy", "1"], fx, raw,
                        lambda after: next((t["title"] for t in after if t["id"] != 1), None))
    raise ValueError(cmd)


def frozen_code_touched(base: Path, repo: Path) -> bool:
    """True if delete_task's body or the CLI `delete` branch changed from the base repo."""
    import ast

    def fn_src(p: Path, name: str) -> str | None:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            return None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                return ast.dump(node)
        return None

    return fn_src(base / "tinytasks/api.py", "delete_task") != fn_src(repo / "tinytasks/api.py", "delete_task")


def _project_key(path: Path) -> str:
    """Claude Code's per-project folder name under ~/.claude/projects (path with : \\ / _ -> -)."""
    import re as _re

    return _re.sub(r"[:\\/_.]", "-", str(path.resolve()))


def auto_memory_files(work_dir: Path) -> list[str]:
    mem = Path.home() / ".claude" / "projects" / _project_key(work_dir) / "memory"
    return sorted(p.name for p in mem.glob("*.md")) if mem.exists() else []


def memory_evidence(run_dir: Path) -> dict:
    ev = {}
    work_dirs = [d for d in (run_dir / "repo", run_dir / "repo_b") if d.exists()]
    ev["auto_memory_files"] = {d.name: auto_memory_files(d) for d in work_dirs}
    s1 = run_dir / "snap_s1"
    tracked = subprocess.run(["git", "ls-files", "CLAUDE.md"], cwd=s1, capture_output=True, text=True).stdout.strip() \
        if (s1 / ".git").exists() else ""
    ev["claude_md_after_s1"] = {"exists": (s1 / "CLAUDE.md").exists(), "committed": bool(tracked)}
    for s in ("session_1", "session_2", "session_3", "session_4"):
        log = run_dir / f"{s}.jsonl"
        tools = []
        if log.exists():
            for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") != "assistant":
                    continue
                for block in (msg.get("message") or {}).get("content") or []:
                    if block.get("type") == "tool_use":
                        name = block.get("name", "")
                        inp = json.dumps(block.get("input", {}))
                        tools.append((name, inp))
        ev[s] = {
            "plexus_recall_calls": sum(1 for n, _ in tools if n.endswith("__recall")),
            "plexus_assert_fact_calls": sum(1 for n, _ in tools if n.endswith("__assert_fact")),
            "read_claude_md": any(n == "Read" and "CLAUDE.md" in i for n, i in tools),
            "wrote_claude_md": any((n in ("Write", "Edit") or n == "Bash") and "CLAUDE.md" in i
                                   and (n != "Bash" or ">" in i or "tee" in i or "cat <<" in i)
                                   for n, i in tools),
            "wrote_auto_memory": any(n in ("Write", "Edit") and "memory" in i and ".claude" in i for n, i in tools),
            "ran_git_log": any(n == "Bash" and "git log" in i for n, i in tools),
            "n_tool_calls": len(tools),
        }
    return ev


def score_run(run_dir: Path, base: Path) -> dict:
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    out = {"run": run_dir.name, "arm": summary["arm"], "handoff": summary.get("handoff", "none"),
           "cost_usd": summary.get("total_cost_usd"), "opportunities": {}, "final_state": {}}
    for session, cmd, rule in OPPORTUNITIES:
        snap = run_dir / SNAP_FOR[session]
        out["opportunities"][cmd] = {"rule": rule, "session": session,
                                     **(score_opportunity(snap, cmd) if snap.exists() else {"verdict": "MISSING"})}
        final = run_dir / "snap_s4"
        if final.exists():
            out["final_state"][cmd] = score_opportunity(final, cmd)["verdict"]
    v = [o["verdict"] for o in out["opportunities"].values()]
    out["violations"] = v.count("VIOLATION")
    out["compliant"] = v.count("COMPLIANT")
    out["broken_or_unclear"] = len(v) - out["violations"] - out["compliant"]
    out["violations_by_session"] = {
        s: sum(1 for o in out["opportunities"].values() if o["session"] == s and o["verdict"] == "VIOLATION")
        for s in ("session_2", "session_3", "session_4")}
    out["frozen_code_touched"] = (run_dir / "snap_s4").exists() and frozen_code_touched(base, run_dir / "snap_s4")
    tests = subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=run_dir / "snap_s4",
                           capture_output=True, text=True, env=_base_env(run_dir / "snap_s4"), timeout=120) \
        if (run_dir / "snap_s4").exists() else None
    out["final_tests_pass"] = tests is not None and tests.returncode == 0
    out["memory_evidence"] = memory_evidence(run_dir)
    return out


if __name__ == "__main__":
    base = Path(__file__).resolve().parent.parent / "repo" / "tinytasks"
    results = [score_run(Path(p), base) for p in sys.argv[1:]]
    print(json.dumps(results, indent=2))
