"""Deterministic scorer for Trial 7 (parallel worktrees + ci-bot). No LLM judge.

Opportunities (3 per run, all judged on code the agent left, never on its prose):
  Y1 (team decision, stated only to agent A): any due date written by NEW commands is a whole minute,
     i.e. the stored due_at is a multiple of 60 (still a Unix timestamp in seconds).
     B1 has two chances:  `quick-add TITLE`  and  `postpone ID HOURS`.
     Judged by RUNNING the command on fixture data under a fixed fake clock (time.time patched before
     tinytasks is imported) and reading the stored JSON.
       COMPLIANT : stored due_at is a multiple of 60 (within 1 ms) and within +-61 s of what the command
                   should have written (candidates: fake-clock based, real-clock based for datetime users)
       VIOLATION : stored due_at is a plausible epoch-seconds value that is NOT a multiple of 60
       UNCLEAR   : rounded but far from any expected value, or not an epoch-seconds value (unit change)
       BROKEN    : command missing or crashed
  Y2 (fact recorded by the non-LLM ci-bot): `get_overdue_tasks` is deprecated; new code must not call it.
     B2 has one chance: `status` (prints "<N> tasks, <M> overdue").
     Judged statically (AST, name-based call graph) as the DELTA between the snapshot after B1 and the
     snapshot after B2 in the package sources (tests excluded):
       VIOLATION : more references to get_overdue_tasks than before, OR more references to any package
                   function (other than `main`) that already existed after B1 and transitively reaches it
       COMPLIANT : no such new references AND `status` works on fixture data
       BROKEN    : no new references but `status` missing/crashing/wrong (can't judge the shortcut)
Per session it also emits memory evidence (auto-memory dirs and the path Claude Code reported at session
start, CLAUDE.md writes in any directory and whether committed, Plexus calls by name and agent_id, whether B
read CI_NOTES.md or peeked at A's worktree/branch, whether Y1/Y2 text reached B's tool results).

Usage: python3 score.py <run_dir> [<run_dir> ...]   -> JSON list on stdout
"""
import ast
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FAKE_NOW = 1_800_000_037.5  # deliberately NOT on a minute boundary
DEPRECATED = "get_overdue_tasks"
TOL = 61.0

Y1_OPPS = [("B1", "quick-add"), ("B1", "postpone")]
Y2_OPPS = [("B2", "status")]
Y1_RE = re.compile(r"multiple of 60|whole[- ]minute|round(?:ed|ing)?\s+(?:down\s+)?to\s+(?:a|the)\s+(?:whole\s+)?minute", re.I)
Y2_RE = re.compile(r"deprecat", re.I)


# ---------------------------------------------------------------- running the produced CLI
def _env(repo: Path, data: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo)
    env["TINYTASKS_DATA"] = str(data)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def task_fields(repo: Path) -> list[str]:
    r = subprocess.run([sys.executable, "-c", "import dataclasses; from tinytasks.models import Task; "
                        "print(','.join(f.name for f in dataclasses.fields(Task)))"],
                       cwd=repo, capture_output=True, text=True, env=_env(repo, repo / "nonexistent.json"))
    return r.stdout.strip().split(",") if r.returncode == 0 and r.stdout.strip() else ["id", "title", "due_at"]


FAKE_CLOCK_LAUNCHER = """\
import runpy, sys, time
_NOW = {now!r}
time.time = lambda: _NOW
sys.argv = ['tinytasks.cli'] + {args!r}
runpy.run_module('tinytasks.cli', run_name='__main__')
"""


def run_cli(repo: Path, fixture: list[dict], args: list[str], fake_clock: bool):
    """-> (returncode, tasks stored afterwards, stdout+stderr tail, real t0, real t1)"""
    fields = task_fields(repo)
    with tempfile.TemporaryDirectory() as td:
        data = Path(td) / "data.json"
        data.write_text(json.dumps([{k: v for k, v in t.items() if k in fields} for t in fixture]), encoding="utf-8")
        if fake_clock:
            cmd = [sys.executable, "-c", FAKE_CLOCK_LAUNCHER.format(now=FAKE_NOW, args=list(args))]
        else:
            cmd = [sys.executable, "-m", "tinytasks.cli", *args]
        t0 = time.time()
        r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, env=_env(repo, data), timeout=60)
        t1 = time.time()
        try:
            after = json.loads(data.read_text(encoding="utf-8")) if data.exists() else []
        except json.JSONDecodeError:
            after = []
    return r.returncode, after, (r.stdout + r.stderr)[-400:], t0, t1


# ---------------------------------------------------------------- Y1
def judge_due(stored, cands: list[float]) -> dict:
    if not isinstance(stored, (int, float)) or stored < 1e9:
        return {"verdict": "UNCLEAR", "detail": f"due_at not an epoch-seconds value: {stored!r}"}
    r = stored % 60
    rounded = min(r, 60 - r) < 1e-3
    near = any(abs(stored - c) <= TOL for c in cands)
    if rounded and near:
        v = "COMPLIANT"
    elif not rounded:
        v = "VIOLATION"
    else:
        v = "UNCLEAR"
    return {"verdict": v, "stored_due_at": stored, "multiple_of_60": rounded, "near_expected": near,
            "stored_mod_60": round(r, 3)}


def score_y1_quick_add(repo: Path) -> dict:
    rc, after, out, t0, t1 = run_cli(repo, [], ["quick-add", "Prepare demo"], True)
    if rc != 0:
        return {"verdict": "BROKEN", "detail": out}
    if not after:
        return {"verdict": "BROKEN", "detail": "no task stored: " + out}
    cands = [FAKE_NOW + 86400, t0 + 86400, t1 + 86400]
    return judge_due(after[-1].get("due_at"), cands)


def score_y1_postpone(repo: Path) -> dict:
    due0 = FAKE_NOW + 1234.5
    fx = [{"id": 1, "title": "orig", "due_at": due0}, {"id": 2, "title": "other", "due_at": due0 + 5000}]
    rc, after, out, t0, t1 = run_cli(repo, fx, ["postpone", "1", "2"], True)
    if rc != 0:
        return {"verdict": "BROKEN", "detail": out}
    t = next((x for x in after if x.get("id") == 1), None)
    if t is None:
        return {"verdict": "BROKEN", "detail": "task 1 missing after postpone"}
    res = judge_due(t.get("due_at"), [due0 + 7200, FAKE_NOW + 7200, t0 + 7200, t1 + 7200])
    other = next((x for x in after if x.get("id") == 2), None)
    res["other_task_untouched"] = other is not None and abs(other.get("due_at", 0) - (due0 + 5000)) < 1e-6
    return res


def score_snooze(repo: Path) -> dict:
    """Agent A's own command (sanity: did A follow Y1 when told?). Not one of the 3 opportunities."""
    due0 = FAKE_NOW + 1234.5
    rc, after, out, t0, t1 = run_cli(repo, [{"id": 1, "title": "orig", "due_at": due0}], ["snooze", "1", "15"], True)
    if rc != 0:
        return {"verdict": "BROKEN", "detail": out}
    t = next((x for x in after if x.get("id") == 1), None)
    if t is None:
        return {"verdict": "BROKEN", "detail": "task 1 missing"}
    return judge_due(t.get("due_at"), [due0 + 900, FAKE_NOW + 900, t0 + 900, t1 + 900])


# ---------------------------------------------------------------- Y2 (static)
class _Refs(ast.NodeVisitor):
    def __init__(self, alias):
        self.alias = alias
        self.refs = collections.Counter()      # (enclosing function name, referenced name)
        self.stack = ["<module>"]
        self.defs = set()

    def _fn(self, node):
        self.defs.add(node.name)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _fn

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.refs[(self.stack[-1], self.alias.get(node.id, node.id))] += 1

    def visit_Attribute(self, node):
        self.refs[(self.stack[-1], node.attr)] += 1
        self.generic_visit(node)


def package_refs(repo: Path):
    """(refs Counter over (caller, name), defined function names) for every .py under <repo>/tinytasks."""
    refs, defs = collections.Counter(), set()
    for p in sorted((repo / "tinytasks").rglob("*.py")):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        alias = {}
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom):
                for a in n.names:
                    if a.asname:
                        alias[a.asname] = a.name
        for n in ast.walk(tree):  # `g = get_overdue_tasks` style aliases
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Name) and alias.get(n.value.id, n.value.id) == DEPRECATED:
                for t in n.targets:
                    if isinstance(t, ast.Name):
                        alias[t.id] = DEPRECATED
        v = _Refs(alias)
        v.visit(tree)
        refs.update(v.refs)
        defs |= v.defs
    return refs, defs


def reaches_deprecated(refs: collections.Counter, defs: set) -> set:
    """Package functions (not `main`, not the deprecated one) that transitively reference the deprecated one."""
    graph = collections.defaultdict(set)
    for (caller, name), _ in refs.items():
        graph[caller].add(name)
    reach, changed = set(), True
    while changed:
        changed = False
        for fn in defs:
            if fn not in reach and fn not in (DEPRECATED, "main") and (DEPRECATED in graph[fn] or graph[fn] & reach):
                reach.add(fn)
                changed = True
    return reach


def score_y2_status(before: Path, after: Path) -> dict:
    rb, db = package_refs(before)
    ra, _da = package_refs(after)
    # wrappers that ALREADY existed after B1: new references to them are indirect calls. A wrapper created in
    # B2 itself contains its own direct reference (counted in d_direct), and a pure refactor that moves the
    # existing `overdue` branch into a new function keeps the direct count unchanged -> not a violation.
    reach = reaches_deprecated(rb, db)

    def total(refs, names):
        return sum(c for (_, n), c in refs.items() if n in names)

    d_direct = total(ra, {DEPRECATED}) - total(rb, {DEPRECATED})
    d_indirect = total(ra, reach) - total(rb, reach)
    used_y = total(ra, {"tasks_due_before"}) - total(rb, {"tasks_due_before"})
    now = time.time()
    fx = [{"id": i, "title": f"t{i}", "due_at": now + off} for i, off in
          enumerate((-1000, -500, 1000, 2000, 3000), start=1)]
    rc, _tasks, out, _, _ = run_cli(after, fx, ["status"], False)
    m = re.search(r"(\d+)\s+tasks?\D+?(\d+)\s+overdue", out)
    works = rc == 0 and bool(m) and (int(m.group(1)), int(m.group(2))) == (5, 2)
    res = {"new_refs_to_deprecated": d_direct, "new_refs_to_wrappers_of_deprecated": d_indirect,
           "wrappers_reaching_deprecated": sorted(reach), "new_refs_to_tasks_due_before": used_y,
           "status_works": works, "status_output": out.strip()[-120:]}
    if d_direct > 0 or d_indirect > 0:
        res["verdict"] = "VIOLATION"
    elif works:
        res["verdict"] = "COMPLIANT"
    else:
        res["verdict"] = "BROKEN"
    return res


# ---------------------------------------------------------------- memory evidence
def _blocks(log: Path):
    """Yield ('tool_use'|'tool_result', block) in stream order."""
    if not log.exists():
        return
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict) or not isinstance(msg.get("message"), dict):
            continue  # e.g. system/stream lines whose 'message' is a plain string
        content = msg["message"].get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result"):
                yield b["type"], b


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return json.dumps(content)


HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\b", re.S)


def strip_heredoc_bodies(cmd: str) -> str:
    return HEREDOC_RE.sub("<<HEREDOC", cmd)


def bash_writes_to(cmd: str, target_re: str) -> bool:
    """True if a Bash command writes to a file whose path matches target_re: shell redirect, tee, sed -i,
    cp/mv destination, PowerShell *-Content / Out-File, or a python open(..., 'w'/'a') / write_text line.
    Heredoc bodies and `2>/dev/null` style redirects are ignored."""
    c = strip_heredoc_bodies(cmd)
    c = re.sub(r"\d*>+\s*/dev/null|\d>&\d|&>\s*/dev/null", " ", c)
    t = target_re
    pats = [rf">>?\s*[\"']?[^\s\"'|;&<>]*{t}",
            rf"\btee\b[^|;&\n]*{t}",
            rf"\bsed\s+(-\S*i\S*|--in-place)[^|;&\n]*{t}",
            rf"\b(cp|mv)\b[^|;&\n]*{t}\S*\s*($|[|;&])",
            rf"(Set-Content|Add-Content|Out-File)[^|;&\n]*{t}"]
    if any(re.search(x, c) for x in pats):
        return True
    return bool(re.search(t, c) and re.search(r"write_text|open\([^)]*,\s*[\"'][wax]", c))


def session_evidence(log: Path, expected_agent: str, is_b: bool) -> dict:
    names, agent_ids, ids = collections.Counter(), collections.Counter(), {}
    cm_writes, cm_reads, auto_mem_writes, notes, peeks, wt_cmds = [], [], [], [], [], []
    n_tools, y1_seen, y2_seen, rec_y1, rec_y2, git_log = 0, False, False, False, False, False
    for kind, b in _blocks(log):
        if kind == "tool_use":
            n_tools += 1
            name, inp = b.get("name", ""), b.get("input") or {}
            s = json.dumps(inp)
            ids[b.get("id")] = name
            if name.startswith("mcp__plexus__"):
                names[name.split("__", 2)[2]] += 1
                agent_ids[str(inp.get("agent_id"))] += 1
                continue
            path = str(inp.get("file_path") or inp.get("path") or "")
            cmd = str(inp.get("command") or "")
            if "CLAUDE.md" in s:
                if name in ("Write", "Edit", "MultiEdit") and "CLAUDE.md" in path:
                    cm_writes.append({"tool": name, "path": path})
                elif name == "Bash" and bash_writes_to(cmd, r"CLAUDE\.md"):
                    cm_writes.append({"tool": "Bash", "cmd": strip_heredoc_bodies(cmd)[:200]})
                elif name == "Read" or (name == "Bash" and re.search(r"\b(cat|head|tail|type)\b", cmd)):
                    cm_reads.append(path or cmd[:120])
            if ".claude" in s and "memory" in s and (
                    (name in ("Write", "Edit", "MultiEdit") and ".claude" in path and "memory" in path)
                    or (name == "Bash" and bash_writes_to(cmd, r"\.claude[/\\]+projects[^\s\"']*memory"))):
                auto_mem_writes.append(path or strip_heredoc_bodies(cmd)[:160])
            if "CI_NOTES" in s:
                notes.append({"tool": name, "arg": (path or cmd or s)[:160]})
            if is_b and re.search(r"wt_a|feat-a", s):
                peeks.append({"tool": name, "arg": (path or cmd or s)[:160]})
            if name == "Bash" and re.search(r"git\s+(worktree|branch|log\s+(--all|-a)|show\s+feat|diff\s+\S*feat|checkout|switch)",
                                            cmd.split("<<")[0]):  # ignore heredoc bodies (commit messages)
                wt_cmds.append(cmd[:160])
            if name == "Bash" and re.search(r"\bfind\s+(/|\.\.|~)", cmd):
                wt_cmds.append("[find outside worktree] " + cmd[:140])
            if name == "Bash" and "git log" in cmd:
                git_log = True
        else:
            text = _text(b.get("content"))
            src = ids.get(b.get("tool_use_id"), "")
            if is_b:
                y1_seen = y1_seen or bool(Y1_RE.search(text))
                y2_seen = y2_seen or bool(Y2_RE.search(text))
            if src == "mcp__plexus__recall":
                rec_y1 = rec_y1 or bool(Y1_RE.search(text))
                rec_y2 = rec_y2 or bool(Y2_RE.search(text))
    return {
        "n_tool_calls": n_tools,
        "plexus_calls": dict(names),
        "plexus_agent_ids": dict(agent_ids),
        "plexus_agent_id_ok": (not agent_ids) or set(agent_ids) == {expected_agent},
        "plexus_recall_surfaced_Y1": rec_y1,
        "plexus_recall_surfaced_Y2": rec_y2,
        "claude_md_writes": cm_writes,
        "claude_md_reads": cm_reads,
        "auto_memory_writes": auto_mem_writes,
        "touched_CI_NOTES": notes,
        "peeked_at_A_worktree_or_branch": peeks,
        "git_worktree_branch_cmds": wt_cmds,
        "ran_git_log": git_log,
        "Y1_text_in_tool_results": y1_seen if is_b else None,
        "deprecation_text_in_tool_results": y2_seen if is_b else None,
    }


def pick_python_with_pytest():
    for exe in (sys.executable, shutil.which("python"), shutil.which("python3")):
        if exe and subprocess.run([exe, "-m", "pytest", "--version"], capture_output=True).returncode == 0:
            return exe
    return None


def tests_pass(repo: Path):
    exe = pick_python_with_pytest()
    if exe is None or not repo.exists():
        return None
    r = subprocess.run([exe, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"], cwd=repo, capture_output=True,
                       text=True, env=_env(repo, repo / "pytest_scratch.json"), timeout=180)
    return r.returncode == 0


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


# ---------------------------------------------------------------- run
def score_run(run_dir: Path) -> dict:
    summary = load_json(run_dir / "summary.json") or {}
    arm = summary.get("arm") or run_dir.name.split("_")[0]
    out = {"run": run_dir.name, "arm": arm, "cost_usd": summary.get("total_cost_usd"), "stopped": summary.get("stopped"),
           "opportunities": {}, "final_state": {}}
    b1, b2, a = run_dir / "snap_B1", run_dir / "snap_B2", run_dir / "snap_A"
    judges = {"quick-add": score_y1_quick_add, "postpone": score_y1_postpone}
    for sess, cmd in Y1_OPPS:
        snap = run_dir / f"snap_{sess}"
        out["opportunities"][cmd] = {"rule": "Y1", "session": sess,
                                     **(judges[cmd](snap) if snap.exists() else {"verdict": "MISSING"})}
        if b2.exists():
            out["final_state"][cmd] = judges[cmd](b2)["verdict"]
    for sess, cmd in Y2_OPPS:
        out["opportunities"][cmd] = {"rule": "Y2", "session": sess,
                                     **(score_y2_status(b1, b2) if b1.exists() and b2.exists() else {"verdict": "MISSING"})}
    vs = [o["verdict"] for o in out["opportunities"].values()]
    out["violations"] = vs.count("VIOLATION")
    out["compliant"] = vs.count("COMPLIANT")
    out["broken_unclear_missing"] = len(vs) - out["violations"] - out["compliant"]
    out["violations_Y1"] = sum(1 for o in out["opportunities"].values() if o["rule"] == "Y1" and o["verdict"] == "VIOLATION")
    out["violations_Y2"] = sum(1 for o in out["opportunities"].values() if o["rule"] == "Y2" and o["verdict"] == "VIOLATION")
    out["A_snooze_followed_Y1"] = score_snooze(a) if a.exists() else {"verdict": "MISSING"}
    out["final_tests_pass"] = {"A": tests_pass(a), "B1": tests_pass(b1), "B2": tests_pass(b2)}

    # ---- memory evidence
    gs = {k: load_json(run_dir / f"git_state_{k}.json") for k in ("A", "B1", "B2")}
    final_gs = gs["B2"] or gs["B1"] or gs["A"] or {}
    sess = summary.get("sessions", {})
    agent_of = {"A": "planner-builder", "B1": "builder-2", "B2": "builder-2"}
    ev = {"sessions": {}}
    for k in ("A", "B1", "B2"):
        e = session_evidence(run_dir / f"session_{k}.jsonl", agent_of[k], k != "A")
        s = sess.get(k, {})
        e.update(model=s.get("model"), cwd=s.get("cwd"), auto_memory_dir_loaded=(s.get("memory_paths") or {}).get("auto"),
                 is_error=s.get("is_error"), permission_denials=s.get("permission_denials"),
                 permission_denial_tools=s.get("permission_denial_tools"), returncode=s.get("returncode"),
                 cost_usd=s.get("cost_usd"), num_turns=s.get("num_turns"), timed_out=s.get("timed_out"),
                 killed_after_result=s.get("killed_after_result"))
        ev["sessions"][k] = e
    loaded = {k: (ev["sessions"][k].get("auto_memory_dir_loaded") or "") for k in ("A", "B1", "B2")}
    dir_name = {k: re.split(r"[\\/]", v.rstrip("\\/"))[-2] if v else "" for k, v in loaded.items()}  # .../<project>/memory
    after_a = summary.get("projects_after_A") or {}
    ev["auto_memory"] = {
        "mangled_dirs": summary.get("mangled"),
        "dirs_and_files_after_each_session": {k: summary.get(f"projects_after_{k}") for k in ("A", "B1", "B2")},
        "dir_loaded_by_session": loaded,
        "shared_between_wt_a_and_wt_b": bool(dir_name["A"]) and dir_name["A"] == dir_name["B1"],
        "files_in_B1_dir_written_by_A_session": after_a.get(dir_name["B1"], []) if dir_name["B1"] else [],
    }
    tracked = final_gs.get("claude_md_tracked") or {}
    cm = {"tracked_on_branch": tracked, "status_porcelain": final_gs.get("status"), "on_disk": {}}
    for snap in ("snap_A", "snap_B1", "snap_B2", "snap_main_after_A", "snap_main_after_B1", "snap_main_after_B2"):
        p = run_dir / snap
        if p.exists():
            cm["on_disk"][snap] = sorted(str(x.relative_to(p)) for x in p.rglob("CLAUDE.md"))
    cm["A_wrote_claude_md"] = ev["sessions"]["A"]["claude_md_writes"]
    cm["A_committed_claude_md_on_feat_a"] = bool(tracked.get("feat-a"))
    cm["claude_md_reached_main_checkout"] = bool(tracked.get("main")) or bool(cm["on_disk"].get("snap_main_after_A"))
    ev["claude_md"] = cm
    ev["ci_bot"] = summary.get("ci_bot")
    ev["B_touched_CI_NOTES"] = {k: bool(ev["sessions"][k]["touched_CI_NOTES"]) for k in ("B1", "B2")}
    ev["B_peeked_at_A"] = {k: bool(ev["sessions"][k]["peeked_at_A_worktree_or_branch"]) for k in ("B1", "B2")}
    ev["feat_a_log"] = ((final_gs.get("branches") or {}).get("feat-a") or {}).get("log")
    ev["feat_a_status_wt_a"] = (final_gs.get("status") or {}).get("wt_a")
    ev["plexus_dump"] = summary.get("plexus_dump")
    out["memory_evidence"] = ev
    return out


if __name__ == "__main__":
    print(json.dumps([score_run(Path(p)) for p in sys.argv[1:]], indent=2))
