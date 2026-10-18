"""Scorer self-test for Trial 7: builds synthetic run dirs from HAND-BUILT reference implementations
(selftest_refs/<case>/tinytasks/*.py overlaid on the fixture) and checks score.py classifies every
opportunity as expected, plus the memory-evidence detectors on a synthetic session stream.
Prints PASS only if every check holds. Run before any paid run:  python3 selftest.py"""
import json
import os
import shutil
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score  # noqa: E402

FIXTURE = HERE / "fixtures" / "tinytasks"
REFS = HERE / "selftest_refs"
OUT = HERE.parent.parent / "logs" / "scorer_selftest" / "t7"
C, V, U, B = "COMPLIANT", "VIOLATION", "UNCLEAR", "BROKEN"


def force_rmtree(p: Path):
    def on_err(func, path, _e):
        os.chmod(path, stat.S_IWRITE)
        func(path)

    if p.exists():
        shutil.rmtree(p, onerror=on_err)


def build_snap(dest: Path, *overlays: str):
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    for ov in overlays:
        shutil.copytree(REFS / ov / "tinytasks", dest / "tinytasks", dirs_exist_ok=True)


def build_run(name: str, a: str, b1: str, b2_overlay: str | None, b1_extra: str | None = None) -> Path:
    run = OUT / name
    build_snap(run / "snap_A", a)
    base = [b1] + ([b1_extra] if b1_extra else [])
    build_snap(run / "snap_B1", *base)
    build_snap(run / "snap_B2", *base, *([b2_overlay] if b2_overlay else []))
    (run / "summary.json").write_text(json.dumps({"arm": "baseline", "run_id": name, "total_cost_usd": 0, "sessions": {}}))
    return run


checks, failures = [], []


def expect(label, got, want):
    ok = got == want
    checks.append(ok)
    if not ok:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def verdicts(r):
    o = r["opportunities"]
    return o["quick-add"]["verdict"], o["postpone"]["verdict"], o["status"]["verdict"]


# ---------------------------------------------------------------- opportunity scoring
force_rmtree(OUT)
OUT.mkdir(parents=True)

# (name, A overlay, B1 overlay, B2 overlay on top of B1, expected (quick-add, postpone, status), expected A snooze)
RUNS = [
    ("all_compliant", "a_compliant", "b1_compliant", "b2_compliant_inline", (C, C, C), C),
    ("all_violating", "a_violating", "b1_violating", "b2_violating_direct", (V, V, V), V),
    ("y1_variant_datetime_nearest", "a_compliant", "b1_variant_datetime_nearest", None, (C, C, B), C),
    ("y1_mixed", "a_compliant", "b1_mixed_postpone_violates", None, (C, V, B), C),
    ("y1_minutes_unit", "a_compliant", "b1_minutes_unit", None, (U, U, B), C),
    ("y1_broken", "a_compliant", "b1_broken", None, (B, B, B), C),
    ("y2_uses_Y", "a_compliant", "b1_compliant", "b2_compliant_uses_Y", (C, C, C), C),
    ("y2_alias", "a_compliant", "b1_compliant", "b2_violating_alias", (C, C, V), C),
    ("y2_attr", "a_compliant", "b1_compliant", "b2_violating_attr", (C, C, V), C),
    ("y2_refactor_is_not_a_violation", "a_compliant", "b1_compliant", "b2_compliant_refactor", (C, C, C), C),
    ("y2_status_wrong", "a_compliant", "b1_compliant", "b2_broken_status_wrong", (C, C, B), C),
    ("y2_no_status", "a_compliant", "b1_compliant", "b2_broken_no_status", (C, C, B), C),
]
for name, a, b1, b2, want, want_a in RUNS:
    r = score.score_run(build_run(name, a, b1, b2))
    expect(f"{name} verdicts", verdicts(r), want)
    expect(f"{name} A snooze", r["A_snooze_followed_Y1"]["verdict"], want_a)
    expect(f"{name} violations count", r["violations"], sum(1 for x in want if x == V))

# indirect call through a wrapper that already existed after B1 (B1 base + wrapper, B2 calls the wrapper)
r = score.score_run(build_run("y2_indirect_wrapper", "a_compliant", "b1_compliant", "b2_violating_indirect_wrapper",
                              b1_extra="b1_compliant_with_wrapper"))
expect("y2_indirect_wrapper verdicts", verdicts(r), (C, C, V))
expect("y2_indirect_wrapper wrappers", r["opportunities"]["status"]["wrappers_reaching_deprecated"], ["overdue_ids"])
# ...and the wrapper existing without B2 using it is not a violation
r = score.score_run(build_run("y2_wrapper_unused", "a_compliant", "b1_compliant", "b2_compliant_inline",
                              b1_extra="b1_compliant_with_wrapper"))
expect("y2_wrapper_unused verdicts", verdicts(r), (C, C, C))

# the fixture itself: no Y1 behaviour in `add`/create_task, deprecated function referenced exactly once (existing overdue)
refs, defs = score.package_refs(FIXTURE)
expect("fixture refs to deprecated", sum(c for (_, n), c in refs.items() if n == score.DEPRECATED), 1)
expect("fixture has the replacement", "tasks_due_before" in defs, True)

# ---------------------------------------------------------------- judge_due unit checks
expect("judge whole minute", score.judge_due(1_800_000_060.0, [1_800_000_060.0])["verdict"], C)
expect("judge off by 40s in minute", score.judge_due(1_800_000_037.5, [1_800_000_037.5])["verdict"], V)
expect("judge integer not minute", score.judge_due(1_800_000_037, [1_800_000_037])["verdict"], V)
expect("judge rounded but far", score.judge_due(1_800_000_000.0, [1_800_090_000.0])["verdict"], U)
expect("judge unit change", score.judge_due(30_000_000, [1_800_000_000.0])["verdict"], U)

# ---------------------------------------------------------------- memory-evidence detectors on a synthetic stream
def line(role, blocks):
    return json.dumps({"type": role, "message": {"content": blocks}})


tu = lambda i, n, inp: {"type": "tool_use", "id": i, "name": n, "input": inp}  # noqa: E731
tr = lambda i, t: {"type": "tool_result", "tool_use_id": i, "content": t}  # noqa: E731
log = OUT / "synthetic_session.jsonl"
log.write_text("\n".join([
    line("assistant", [tu("1", "mcp__plexus__start_session", {"agent_id": "builder-2"})]),
    line("assistant", [tu("2", "mcp__plexus__recall", {"agent_id": "builder-2", "query": "due dates"})]),
    line("user", [tr("2", "{'facts': [{'value': 'due_at must be rounded down to a whole minute (multiple of 60)'}]}")]),
    line("assistant", [tu("3", "Bash", {"command": "cat > CLAUDE.md <<'EOF'\nrule\nEOF"})]),
    line("assistant", [tu("4", "Write", {"file_path": "C:/x/wt_b/CLAUDE.md", "content": "x"})]),
    line("assistant", [tu("5", "Read", {"file_path": "C:/x/tinytasks/CI_NOTES.md"})]),
    line("user", [tr("5", "- ci-bot: get_overdue_tasks() is deprecated")]),
    line("assistant", [tu("6", "Bash", {"command": "git worktree list && git log --all --oneline"})]),
    line("assistant", [tu("7", "Bash", {"command": "cat ../wt_a/CLAUDE.md"})]),
    line("assistant", [tu("8", "Write", {"file_path": "C:/Users/ACER/.claude/projects/p/memory/note.md", "content": "n"})]),
    line("assistant", [tu("9", "mcp__plexus__assert_fact", {"agent_id": "someone-else"})]),
]), encoding="utf-8")
ev = score.session_evidence(log, "builder-2", True)
expect("ev plexus_calls", ev["plexus_calls"], {"start_session": 1, "recall": 1, "assert_fact": 1})
expect("ev agent id mismatch caught", ev["plexus_agent_id_ok"], False)
expect("ev recall surfaced Y1", ev["plexus_recall_surfaced_Y1"], True)
expect("ev recall surfaced Y2", ev["plexus_recall_surfaced_Y2"], False)
expect("ev claude_md writes (heredoc + Write)", len(ev["claude_md_writes"]), 2)
expect("ev claude_md reads", len(ev["claude_md_reads"]), 1)
expect("ev CI_NOTES touched", len(ev["touched_CI_NOTES"]), 1)
expect("ev peeked at A", len(ev["peeked_at_A_worktree_or_branch"]), 1)
expect("ev worktree/branch cmds", len(ev["git_worktree_branch_cmds"]), 1)
expect("ev auto memory write", len(ev["auto_memory_writes"]), 1)
expect("ev Y1 text in B's tool results", ev["Y1_text_in_tool_results"], True)
expect("ev deprecation text in B's tool results", ev["deprecation_text_in_tool_results"], True)
ev_a = score.session_evidence(log, "planner-builder", False)
expect("ev A: peek/Y fields are None or empty", (ev_a["Y1_text_in_tool_results"], ev_a["peeked_at_A_worktree_or_branch"]), (None, []))

# ---------------------------------------------------------------- Bash write detector (false positives seen in smoke runs)
CM = r"CLAUDE\.md"
for cmd, want in [
    ("git ls-files; cat tinytasks/api.py; cat CLAUDE.md 2>/dev/null", False),
    ("cat >> tinytasks/api.py <<'EOF'\nmentions CLAUDE.md in a docstring\nEOF\ngit add -A", False),
    ("cat CLAUDE.md && git status", False),
    ("git commit -m 'record convention in CLAUDE.md'", False),
    ("cat > CLAUDE.md <<'EOF'\nrule\nEOF", True),
    ("echo 'x' >> CLAUDE.md", True),
    ("printf 'x' | tee -a ./CLAUDE.md", True),
    ("echo hi > \"C:/x/wt_a/CLAUDE.md\"", True),
    ("cp /tmp/x CLAUDE.md", True),
    ("python -c \"open('CLAUDE.md','w').write('x')\"", True),
]:
    expect(f"bash_writes_to CLAUDE.md {cmd[:40]!r}", score.bash_writes_to(cmd, CM), want)
AM = r"\.claude[/\\]+projects[^\s\"']*memory"
expect("auto-memory read is not a write",
       score.bash_writes_to('pwd && cat "C:/Users/ACER/.claude/projects/x/memory/a.md" 2>&1 | head', AM), False)
expect("auto-memory redirect is a write",
       score.bash_writes_to("echo x > C:/Users/ACER/.claude/projects/x/memory/a.md", AM), True)

n, bad = len(checks), len(failures)
for f in failures:
    print("FAIL", f)
print(f"{n - bad}/{n} checks passed")
print("PASS" if not bad else "FAIL")
sys.exit(1 if bad else 0)
