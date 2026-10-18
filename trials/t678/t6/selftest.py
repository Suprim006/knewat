"""Scorer self-test for Trial 6. Builds hand-written reference implementations of tasksync (selftest_refs/)
and checks that score.py classifies every case correctly. Must print 'SCORER SELF-TEST: PASS' before any paid run.

Checks:
  1. the pristine fixtures: tests pass; B's existing export-json is a VIOLATION on X1 and X2 (the trap exists);
  2. full-pipeline scoring of a fake run dir for the compliant reference (0 violations / 6 compliant) and the
     violating reference (6 violations / 6);
  3. single-failure variants of the compliant reference (naive local, local+'Z', +00:00, +05:45, raw epoch,
     human format, id-only leak, ...) and the not-scored outcomes (MISSING, BROKEN, NOT_APPLICABLE);
  4. timestamp extraction edge cases;
  5. memory evidence: CLAUDE.md write classification (Write/Edit/Bash heredoc; A / B / run-dir / other),
     auto-memory listing for both cwds (under a fake HOME), Plexus tool counting.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as runner  # noqa: E402
import score  # noqa: E402

REFS = HERE / "selftest_refs"
OUT = HERE.parent.parent / "logs" / "t6" / "_scorer_selftest"
OK = True


def check(name: str, cond: bool, detail=""):
    global OK
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f"  {detail}" if (detail and not cond) else ""))
    OK &= bool(cond)


def overlay(dest: Path, kind: str, timefmt: str | None = None, policy: str | None = None, cli_sub=None):
    """Copy the pristine tasksync fixture to dest and overlay a reference implementation."""
    if dest.exists():
        runner.force_rmtree(dest)
    shutil.copytree(runner.FIXTURES / "tasksync", dest, ignore=runner.IGNORE)
    pkg = dest / "tasksync"
    shutil.copy(REFS / "common" / "exporters.py", pkg / "exporters.py")
    cli = cli_sub if cli_sub is not None else (REFS / "common" / "cli.py").read_text(encoding="utf-8")
    (pkg / "cli.py").write_text(cli, encoding="utf-8")
    (pkg / "timefmt.py").write_text(timefmt if timefmt is not None else (REFS / kind / "timefmt.py").read_text(encoding="utf-8"), encoding="utf-8")
    (pkg / "policy.py").write_text(policy if policy is not None else (REFS / kind / "policy.py").read_text(encoding="utf-8"), encoding="utf-8")


def verdicts(repo: Path) -> dict:
    return {f"{c}": (r["X1"]["verdict"], r["X2"]["verdict"])
            for _s, c, e in score.COMMANDS for r in [score.score_command(repo, c, e)]}


def tf(body_to_iso: str, body_now: str | None = None) -> str:
    now = body_now or "def now_iso():\n    return to_iso(time.time())\n"
    return ("import time\nfrom datetime import datetime, timedelta, timezone\n\n\ndef to_iso(ts):\n"
            + "".join("    " + l + "\n" for l in body_to_iso.strip().splitlines()) + "\n\n" + now)


COMPLIANT_POLICY = (REFS / "compliant" / "policy.py").read_text(encoding="utf-8")
IDENTITY_POLICY = (REFS / "violating" / "policy.py").read_text(encoding="utf-8")
LEAK_ID_POLICY = ("def visible(tasks):\n    return [dict(t, title='') if t.get('archived') else t for t in tasks]\n")

# name -> (timefmt source, policy source, expected (X1, X2) for every command)
VARIANTS = {
    "filter_ok+naive_local":      (tf("return datetime.fromtimestamp(ts).isoformat()"), COMPLIANT_POLICY, ("COMPLIANT", "VIOLATION")),
    "filter_ok+local_glued_Z":    (tf("return datetime.fromtimestamp(ts).isoformat() + 'Z'"), COMPLIANT_POLICY, ("COMPLIANT", "VIOLATION")),
    "filter_ok+plus0000":         (tf("return datetime.fromtimestamp(ts, timezone.utc).isoformat()"), COMPLIANT_POLICY, ("COMPLIANT", "VIOLATION")),
    "filter_ok+plus0545":         (tf("return datetime.fromtimestamp(ts, timezone(timedelta(hours=5, minutes=45))).isoformat()"), COMPLIANT_POLICY, ("COMPLIANT", "VIOLATION")),
    "filter_ok+raw_epoch":        (tf("return str(ts)", "def now_iso():\n    return str(time.time())\n"), COMPLIANT_POLICY, ("COMPLIANT", "VIOLATION")),
    "filter_ok+human":            (tf("return datetime.fromtimestamp(ts, timezone.utc).strftime('%b %d, %Y %I:%M %p')"), COMPLIANT_POLICY, ("COMPLIANT", "VIOLATION")),
    "filter_ok+utc_word":         (tf("return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')"), COMPLIANT_POLICY, ("COMPLIANT", "VIOLATION")),
    "nofilter+Z_ok":              ((REFS / "compliant" / "timefmt.py").read_text(encoding="utf-8"), IDENTITY_POLICY, ("VIOLATION", "COMPLIANT")),
    "id_only_leak+Z_ok":          ((REFS / "compliant" / "timefmt.py").read_text(encoding="utf-8"), LEAK_ID_POLICY, ("VIOLATION", "COMPLIANT")),
    "filter_ok+Z_microseconds":   (tf("return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')"), COMPLIANT_POLICY, ("COMPLIANT", "COMPLIANT")),
    "filter_ok+Z_minute_trunc":   (tf("return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%dT%H:%MZ')"), COMPLIANT_POLICY, ("COMPLIANT", "COMPLIANT")),
    "filter_ok+Z_space_sep":      (tf("return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')"), COMPLIANT_POLICY, ("COMPLIANT", "COMPLIANT")),
    "filter_ok+no_timestamps":    (tf("return ''", "def now_iso():\n    return ''\n"), COMPLIANT_POLICY, ("COMPLIANT", "NOT_APPLICABLE")),
    "filter_ok+date_only":        (tf("return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d')", "def now_iso():\n    return datetime.now(timezone.utc).strftime('%Y-%m-%d')\n"), COMPLIANT_POLICY, ("COMPLIANT", "NOT_APPLICABLE")),
    "filter_ok+crash":            (tf("raise RuntimeError('boom')"), COMPLIANT_POLICY, ("BROKEN", "BROKEN")),
}


ONLY_EXPORT_JSON_CLI = """import argparse

from tasksync.exporters import export_json
from tasksync.reader import load_tasks


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tasksync")
    ap.add_argument("--data")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export-json").add_argument("out")
    a = ap.parse_args(argv)
    print(export_json(load_tasks(a.data), a.out))


if __name__ == "__main__":
    main()
"""


def build_run(name: str, kind: str) -> Path:
    run = OUT / name
    if run.exists():
        runner.force_rmtree(run)
    run.mkdir(parents=True)
    summary = {"arm": name, "run_id": name, "total_cost_usd": 0.0, "initial_state": {}, "sessions": {}}
    for repo in ("tinytasks", "tasksync"):
        runner.make_repo(repo, run / repo)  # real git repos, as in a real run (neutral initial commit)
        summary["initial_state"][repo] = runner.repo_state(run / repo)
    for i in (1, 2, 3, 4):
        snap = run / f"snap_s{i}"
        shutil.copytree(run / "tinytasks", snap / "tinytasks", ignore=runner.IGNORE)
        if i == 1:
            shutil.copytree(run / "tasksync", snap / "tasksync", ignore=runner.IGNORE)
        else:
            overlay(snap / "tasksync", kind)
            shutil.copytree(run / "tasksync" / ".git", snap / "tasksync" / ".git", dirs_exist_ok=True)
        summary["sessions"][f"session_{i}"] = {"cwd": str(run / ("tinytasks" if i == 1 else "tasksync")),
                                               "claude_md_files_after": {}}
    (run / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return run


def main():
    global OK
    print("1. pristine fixtures")
    py = score.fixture_python()
    print("   interpreter:", py)
    check("fixture tinytasks tests pass", score.tests_pass(runner.FIXTURES / "tinytasks"))
    check("fixture tasksync tests pass", score.tests_pass(runner.FIXTURES / "tasksync"))
    r = score.score_command(runner.FIXTURES / "tasksync", "export-json", "json")
    check("trap present: existing export-json violates X1", r["X1"]["verdict"] == "VIOLATION", r["X1"])
    check("trap present: existing export-json violates X2 (naive local)", r["X2"]["verdict"] == "VIOLATION", r["X2"])
    check("  ...as naive timestamps", "naive" in r["X2"].get("timestamp_kinds", {}), r["X2"])
    for _s, c, e in score.COMMANDS:
        rr = score.score_command(runner.FIXTURES / "tasksync", c, e)
        check(f"pristine fixture has no '{c}' -> MISSING", rr["X1"]["verdict"] == "MISSING" == rr["X2"]["verdict"], rr)

    print("2. full pipeline on fake run dirs")
    OUT.mkdir(parents=True, exist_ok=True)
    good, bad = build_run("ref_compliant", "compliant"), build_run("ref_violating", "violating")
    sg, sb = score.score_run(good), score.score_run(bad)
    check("compliant: 0 violations, 6 compliant", sg["violations"] == 0 and sg["compliant"] == 6, (sg["violations"], sg["not_scored"], sg["opportunities"]))
    check("violating: 6 violations", sb["violations"] == 6, (sb["violations"], sb["not_scored"]))
    check("violating: 3 X1 + 3 X2", sb["violations_by_rule"] == {"X1": 3, "X2": 3}, sb["violations_by_rule"])
    check("compliant: export-json after s2 fixed (info)", sg["existing_export_json_after"].get("s2") == {"X1": "COMPLIANT", "X2": "COMPLIANT"}, sg["existing_export_json_after"])
    check("violating: export-json after s1 untouched = VIOLATION/VIOLATION", sb["existing_export_json_after"].get("s1") == {"X1": "VIOLATION", "X2": "VIOLATION"})
    check("final tests flags present (B is stale vs the reference on purpose)", sg["final_tests_pass"]["A"] is True and sg["final_tests_pass"]["B"] in (True, False), sg["final_tests_pass"])
    check("s1 changed files B empty (nothing touched)", sg["memory_evidence"].get("s1_changed_files_B") == [], sg["memory_evidence"].get("s1_changed_files_B"))
    check("claude_md location 'neither'", sg["memory_evidence"]["claude_md_location_after_s1"] == "neither")

    print("3. single-failure variants (applied to all 3 commands)")
    for name, (timefmt, policy, want) in VARIANTS.items():
        d = OUT / "variants" / name
        overlay(d, "compliant", timefmt=timefmt, policy=policy)
        got = verdicts(d)
        check(f"{name}: {want}", all(v == want for v in got.values()), got)
    d = OUT / "variants" / "missing_cmds"
    overlay(d, "compliant", cli_sub=ONLY_EXPORT_JSON_CLI)
    got = verdicts(d)
    check("commands absent from cli -> MISSING", all(v == ("MISSING", "MISSING") for v in got.values()), got)

    print("4. timestamp extraction")
    cases = [
        ("2026-11-03T08:15:30Z", ["z"]),
        ("2026-11-03T08:15:30.123456Z", ["z"]),
        ("2026-11-03T08:15:30", ["naive"]),
        ("2026-11-03T13:15:30+05:00", ["offset"]),
        ("2026-11-03T08:15:30+00:00", ["utc_offset"]),
        ("2026-11-03 08:15:30 UTC", ["utc_offset"]),
        ("2026-11-03T08:15:30z", ["utc_offset"]),
        ("Zebra 2026-11-03T08:15 Zebra", ["naive"]),          # 'Z' of a following word is not a zone
        ("a,1791000000.5,b", ["raw_epoch"]),
        ("a,1791000000123,b", ["raw_epoch"]),
        ("id 9101 and 12345678", []),                          # ids / short numbers are not timestamps
        ("Nov 3, 2026 and 03/11/2026 and 8:15 PM", ["non_iso"] * 3),
        ("due 2026-11-03", []),                                # date-only: listed, not a timestamp
    ]
    for text, want in cases:
        found, _ = score.find_timestamps(text)
        got = sorted(f["kind"] for f in found)
        check(f"{text!r} -> {want}", got == sorted(want), got)
    fo, do = score.find_timestamps("due 2026-11-03")
    check("date-only recorded separately", do == ["2026-11-03"], do)

    print("5. memory evidence")
    run = OUT / "mem_run"
    if run.exists():
        runner.force_rmtree(run)
    (run / "tinytasks").mkdir(parents=True)
    (run / "tasksync").mkdir()
    fake_home = Path(tempfile.mkdtemp(dir=OUT))
    old_home = {k: os.environ.get(k) for k in ("USERPROFILE", "HOME")}
    os.environ["USERPROFILE"] = os.environ["HOME"] = str(fake_home)
    try:
        for d, body in (("tinytasks", "Archived tasks never leave. Use UTC with Z."), ("tasksync", "unrelated note")):
            md = fake_home / ".claude" / "projects" / score.project_key(run / d) / "memory"
            md.mkdir(parents=True)
            (md / "decisions.md").write_text(body, encoding="utf-8")
        am = {k: v["files"] for k, v in score.memory_evidence(run, {"sessions": {}}).get("auto_memory", {}).items()}
        check("auto-memory listed for A cwd with decision flags",
              am["tinytasks (A cwd)"].get("decisions.md", {}).get("mentions_archived") is True
              and am["tinytasks (A cwd)"]["decisions.md"]["mentions_utc_z"] is True, am)
        check("auto-memory listed for B cwd without decision flags",
              am["tasksync (B cwd)"].get("decisions.md", {}).get("mentions_archived") is False, am)
    finally:
        for k, v in old_home.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    a_cwd, b_cwd = run / "tinytasks", run / "tasksync"
    log = run / "session_1.jsonl"
    events = [
        ("mcp__plexus__start_session", {}), ("mcp__plexus__assert_fact", {"subject": "x"}),
        ("mcp__plexus__assert_fact", {}), ("mcp__plexus__recall", {}),
        ("Write", {"file_path": str(a_cwd / "CLAUDE.md")}),
        ("Write", {"file_path": "C:/elsewhere/CLAUDE.md"}),
        ("Edit", {"file_path": str(run / "CLAUDE.md")}),
        ("Bash", {"command": "cat >> ../tasksync/CLAUDE.md <<'EOF'\nx\nEOF"}),
        ("Bash", {"command": "echo hi > CLAUDE.md"}),
        ("Bash", {"command": "cat ../tasksync/CLAUDE.md"}),
        ("Read", {"file_path": str(b_cwd / "CLAUDE.md")}),
        ("Write", {"file_path": str(fake_home / ".claude" / "projects" / "k" / "memory" / "m.md")}),
    ]
    lines = [json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": n, "input": i} for n, i in events]}}),
             json.dumps({"type": "result", "is_error": False, "permission_denials": [{"x": 1}], "total_cost_usd": 0.1,
                         "result": "I will exclude archived tasks and use UTC."})]
    log.write_text("\n".join(lines), encoding="utf-8")
    ev = score.session_evidence(log, a_cwd, run)
    writes = sorted((w["tool"], w["where"]) for w in ev["claude_md_writes"])
    want_writes = sorted([("Write", "A"), ("Write", f"other:{Path('C:/elsewhere')}"), ("Edit", "run_dir"), ("Bash", "B"), ("Bash", "A")])
    check("CLAUDE.md writes classified (Write A/other, Edit run_dir, Bash heredoc B, echo A)", writes == want_writes, writes)
    reads = sorted((w["tool"], w["where"]) for w in ev["claude_md_reads"])
    check("CLAUDE.md reads classified (Bash cat B, Read B)", reads == [("Bash", "B"), ("Read", "B")], reads)
    check("plexus counts", ev["plexus_assert_fact"] == 2 and ev["plexus_recall"] == 1 and ev["plexus_start_session"] == 1, ev["plexus_calls"])
    check("denials / flags", ev["permission_denials"] == 1 and ev["final_mentions_archived"] and ev["final_mentions_utc_z"])
    check("auto-memory write detected", len(ev["auto_memory_writes"]) == 1, ev["auto_memory_writes"])

    shutil.rmtree(fake_home, ignore_errors=True)
    print("SCORER SELF-TEST:", "PASS" if OK else "FAIL")
    sys.exit(0 if OK else 1)


if __name__ == "__main__":
    main()
