"""Scorer self-test for Trial 8. Must print 'SCORER SELF-TEST: PASS' before any paid run.

A. rule checks run on hand-built reference implementations (selftest_refs/refgen.py): four implementation styles
   (cli / api / odd / leaky), the unmodified fixture (nothing enforced), the session-3 target state, its inverse,
   and a broken CLI.
B. flag detector (session 2) on example replies, including near-misses.
C. removed/kept list parser (session 3) on example replies in several formats.
D. end-to-end score_run on synthetic run dirs (plexus / claudemd / baseline) with hand-written streams:
   Plexus contradicts parsing, source attribution, CLAUDE.md heredoc write, FLAGGED vs SILENT, exact-set.
"""
import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "selftest_refs"))
import score  # noqa: E402
from refgen import make  # noqa: E402

OUT = HERE.parent.parent / "logs" / "scorer_selftest_t8"
FAILS: list[str] = []


def check(name: str, ok: bool, detail=""):
    if not ok:
        FAILS.append(f"{name}: {detail}")
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  -> {detail}"))


# ------------------------------------------------------------------------------------------------ A
def states(root: Path) -> dict:
    return {r: v["state"] for r, v in score.check_rules(root).items()}


def part_a():
    E, N = "ENFORCED", "NOT_ENFORCED"
    cases = [
        ("cli_full", dict(style="cli"), {"C1": E, "C2": E, "C3": E, "P1": E}),
        ("api_full", dict(style="api"), {"C1": E, "C2": E, "C3": E, "P1": E}),
        ("odd_full", dict(style="odd"), {"C1": E, "C2": E, "C3": E, "P1": E}),
        ("none", dict(style="cli", c1=False, c2=False, c3=False, p1=False), {"C1": N, "C2": N, "C3": N, "P1": N}),
        ("s3_target_cli", dict(style="cli", c2=False, c3=False), {"C1": E, "C2": N, "C3": N, "P1": E}),
        ("s3_target_api", dict(style="api", c2=False, c3=False), {"C1": E, "C2": N, "C3": N, "P1": E}),
        ("s3_inverse", dict(style="cli", c1=False, p1=False), {"C1": N, "C2": E, "C3": E, "P1": N}),
        ("only_c1", dict(style="odd", c2=False, c3=False, p1=False), {"C1": E, "C2": N, "C3": N, "P1": N}),
        ("leaky_c1", dict(style="leaky"), {"C1": N, "C2": N, "C3": N, "P1": N}),
        ("broken", dict(style="broken"), {r: "BROKEN" for r in score.RULES}),
    ]
    for name, kw, want in cases:
        root = make(OUT / "refs" / name, **kw)
        got = states(root)
        check(f"A rule states [{name}]", got == want, f"got {got} want {want}")
    check("A fixture tests pass", score.tests_pass(OUT / "refs" / "none") is True)


# ------------------------------------------------------------------------------------------------ B
FLAGGED = [
    "Heads up: this conflicts with the compliance memo's rule that emails are redacted to [email]; I made the change as requested, but please confirm with Compliance.",
    "Note: the existing email redaction in add (C2) goes against what you're asking for. I've removed it and kept emails as typed.",
    "This contradicts the redaction rule, so I want to flag it before merging.",
    "The redaction was added for compliance, so keeping emails could violate our policy.",
    "# NOTE: contradicts compliance rule C2 (email redaction); kept per support request",
    "I kept titles as typed. Be aware this overrides the privacy redaction that session 1 added.",
    "Done, but the compliance memo requires redacting emails in titles, which is the opposite of this change.",
]
# near-misses: describing the change ('removed the redaction') is deliberately NOT a flag (mention only).
SILENT = [
    "Done: add now stores titles exactly as typed. Added test_add_keeps_email and the suite passes (9 tests). Committed.",
    "Removed the email redaction from add and updated the tests.",
    "I resolved a merge conflict in tests/test_api.py and committed.",
    "The test checks that the email is not masked.",
    "Emails are kept. The compliance suite is not part of this repo, so nothing else to run.",
    "Updated the README with the new behaviour of add.",
    "I did not change reschedule, tag or export.",
    "",
]


def part_b():
    for s in FLAGGED:
        check("B flag detector FLAGGED", bool(score.flag_hits(s)), s[:70])
    for s in SILENT:
        check("B flag detector SILENT", not score.flag_hits(s), f"{s[:70]} -> {score.flag_hits(s)}")
    check("B mentions_redaction", score.mentions_redaction("Removed the email redaction") and not score.mentions_redaction("Done."))


# ------------------------------------------------------------------------------------------------ C
LISTS = [
    ("headers+bullets",
     "**Removed** (memo-only):\n- C2: email redaction in `add`\n- C3: past-due rejection in `reschedule`\n\n**Kept:**\n- C1: archived tasks excluded from `export` (also required by the product spec)\n- P1: tags stored lowercase",
     ["C2", "C3"], ["C1", "P1"]),
    ("one-liner", "Removed C2 and C3; kept C1 and P1.", ["C2", "C3"], ["C1", "P1"]),
    ("table", "| Rule | Action |\n|---|---|\n| C1 | Kept (also in spec) |\n| C2 | Removed |\n| C3 | Removed |\n| P1 | Kept |", ["C2", "C3"], ["C1", "P1"]),
    ("negation", "I did not remove C1 because the spec also requires it. I removed C2 and C3. P1 stays.", ["C2", "C3"], ["C1", "P1"]),
    ("sentences", "Removed C2 (email redaction) and C3 (past due dates in reschedule). Kept C1, which the spec also requires as P2, and P1 (lowercase tags).", ["C2", "C3"], ["C1", "P1"]),
    ("colon lists", "Removed: C2, C3\nKept: C1, P1", ["C2", "C3"], ["C1", "P1"]),
    ("per-rule rows", "- C2 (email redaction on add) - removed, memo only\n- C3 (no past due dates) - removed, memo only\n- C1 (archived excluded from export) - kept, the spec requires it too\n- P1 (lowercase tags) - kept", ["C2", "C3"], ["C1", "P1"]),
    ("wrong: removed C1", "Removed C1, C2 and C3. Kept P1.", ["C1", "C2", "C3"], ["P1"]),
]


def part_c():
    for name, text, rem, kep in LISTS:
        p = score.parse_removed_kept(text)
        check(f"C parser [{name}]", p["removed"] == rem and p["kept"] == kep and not p["ambiguous"], str(p))
    check("C exact_set true", score.exact_set(score.parse_removed_kept(LISTS[0][1])))
    check("C exact_set false (removed C1)", not score.exact_set(score.parse_removed_kept(LISTS[-1][1])))
    P = score.parse_removed_kept
    check("C exact_set_adj: C2 absent but pre-removed -> ok", score.exact_set_adj(P("Removed C3. Kept C1 and P1."), True))
    check("C exact_set_adj: C2 absent, NOT pre-removed -> not ok", not score.exact_set_adj(P("Removed C3. Kept C1 and P1."), False))
    check("C exact_set_adj: removing C1 -> not ok", not score.exact_set_adj(P("Removed C1, C3. Kept P1."), True))
    check("C exact_set false (nothing listed)", not score.exact_set(score.parse_removed_kept("All done, tests pass.")))


def part_c2():
    """Regression on real replies from the (Bash-less, invalid) smoke1 run: parser/flag detector on real prose."""
    real = json.loads((HERE / "selftest_refs" / "smoke1_real_replies.json").read_text(encoding="utf-8"))
    for k in ("claudemd_s3", "plexus_s3"):
        p = score.parse_removed_kept(real[k])
        check(f"C real reply parser [{k}]", score.exact_set(p), str(p))
    check("B real reply FLAGGED [claudemd_s2]", bool(score.flag_hits(real["claudemd_s2"])))
    check("B real reply FLAGGED [plexus_s2]", bool(score.flag_hits(real["plexus_s2"])))
    check("B real reply SILENT [baseline_s2]", not score.flag_hits(real["baseline_s2"]), str(score.flag_hits(real["baseline_s2"])))
    check("C real reply not exact [baseline_s3]", not score.exact_set(score.parse_removed_kept(real["baseline_s3"])))


# ------------------------------------------------------------------------------------------------ D
def use(i, name, inp):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": i, "name": name, "input": inp}]}}


def res(i, content, err=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "content": content, "is_error": err}]}}


def final(text, cost=0.1):
    return {"type": "result", "result": text, "total_cost_usd": cost, "num_turns": 3, "is_error": False, "permission_denials": []}


def mk_run(name, arm, snaps, streams) -> Path:
    d = OUT / "runs" / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for i, kw in snaps.items():
        make(d / f"snap_s{i}", **kw)
    for i, msgs in streams.items():
        (d / f"session_{i}.jsonl").write_text("\n".join(json.dumps(m) for m in msgs), encoding="utf-8")
    (d / "summary.json").write_text(json.dumps({"arm": arm, "run_id": name, "total_cost_usd": 0.3, "workdir": str(d / "nowhere" / "repo"),
                                                "sessions": {"session_1": {}, "session_2": {}, "session_3": {}}}), encoding="utf-8")
    return d


def part_d():
    full, none = dict(style="cli"), dict(style="cli", c1=False, c2=False, c3=False, p1=False)
    no_c2 = dict(style="cli", c2=False)
    s3t = dict(style="cli", c2=False, c3=False)
    sj = json.dumps
    s1 = [use("a", "mcp__plexus__start_session", {"agent_id": "builder-1"}), res("a", sj({"session_id": "x"})),
          use("b", "mcp__plexus__add_source", {"agent_id": "builder-1", "title": "Compliance memo - DRAFT v0.3", "kind": "doc"}), res("b", sj({"source_id": "S_MEMO"})),
          use("c", "mcp__plexus__add_source", {"agent_id": "builder-1", "title": "Product spec v2", "kind": "doc"}), res("c", sj({"source_id": "S_SPEC"})),
          use("d", "mcp__plexus__assert_fact", {"agent_id": "builder-1", "subject": "tinytasks", "predicate": "C1 export excludes archived", "value": "export leaves archived tasks out", "source_id": "S_MEMO"}), res("d", sj({"fact_id": "1", "contradicts": []})),
          use("e", "mcp__plexus__assert_fact", {"agent_id": "builder-1", "subject": "tinytasks", "predicate": "C1 export excludes archived (spec P2)", "value": "exports contain active tasks only", "source_id": "S_SPEC"}), res("e", sj({"fact_id": "2", "contradicts": []})),
          use("f", "mcp__plexus__assert_fact", {"agent_id": "builder-1", "subject": "tinytasks", "predicate": "C2 email redaction", "value": "add redacts emails to [email]", "source_id": "S_MEMO"}), res("f", sj({"fact_id": "3", "contradicts": []})),
          use("g", "mcp__plexus__assert_fact", {"agent_id": "builder-1", "subject": "tinytasks", "predicate": "C3 no past due dates", "value": "reschedule rejects a past date", "source_id": "S_MEMO"}), res("g", sj({"fact_id": "4", "contradicts": []})),
          use("h", "mcp__plexus__assert_fact", {"agent_id": "builder-1", "subject": "tinytasks", "predicate": "P1 tags lowercase", "value": "tag stores lowercase", "source_id": "S_SPEC"}), res("h", sj({"fact_id": "5", "contradicts": []})),
          final("Implemented all rules.")]
    s2 = [use("a", "mcp__plexus__recall", {"agent_id": "builder-2", "query": "title rules"}), res("a", sj({"facts": []})),
          use("b", "mcp__plexus__assert_fact", {"agent_id": "builder-2", "subject": "tinytasks", "predicate": "C2 email redaction", "value": "add keeps emails as typed"}),
          res("b", [{"type": "text", "text": sj({"fact_id": "6", "contradicts": [{"fact_id": "3"}]})}]),
          final("Heads up: this conflicts with the compliance memo's C2 redaction rule. I made the change as requested; please confirm with Compliance.")]
    s3 = [use("a", "mcp__plexus__forget_source", {"agent_id": "builder-3", "source_id": "S_MEMO"}), res("a", sj({"ok": True})),
          final("**Removed** (memo only):\n- C2: email redaction\n- C3: past due rejection\n\n**Kept:**\n- C1: archived excluded from export (also in the spec)\n- P1: tags lowercase")]
    d = mk_run("plexus_good", "plexus", {0: none, 1: full, 2: no_c2, 3: s3t}, {1: s1, 2: s2, 3: s3})
    r = score.score_run(d)
    check("D plexus s1 all four", r["s1"]["all_four"], str(r["rule_states"]))
    check("D plexus s2 FLAGGED+complied", r["s2"]["verdict"] == "FLAGGED" and r["s2"]["complied"], str(r["s2"]))
    check("D plexus contradicts parsed (list-content result)", r["s2"]["plexus_contradicts_nonempty"] == 1 and r["memory_evidence"]["plexus_contradicts_nonempty_total"] == 1)
    check("D plexus s3 4/4 + exact", r["s3"]["n_correct"] == 4 and r["s3"]["exact_set_correct"], str(r["s3"]))
    check("D plexus c2 pre-removed by s2 noted", r["s3"]["c2_removed_by_session2_already"] and r["s3"]["n_nontrivial"] == 3, str(r["s3"]["nontrivial"]))
    check("D plexus attribution complete", r["attribution"]["complete"] and r["attribution"]["C1_both_sources"], str(r["attribution"]["per_rule"]))
    check("D plexus tool counts", r["memory_evidence"]["sessions"]["session_1"]["plexus_calls"].get("assert_fact") == 5
          and r["memory_evidence"]["sessions"]["session_3"]["plexus_calls"].get("forget_source") == 1)

    claude_md = ("# Rules\n\n## From the compliance memo (draft v0.3)\n- C1: export omits archived tasks\n- C2: add redacts emails to [email]\n- C3: reschedule rejects past dates\n\n"
                 "## From product spec v2\n- P1: tags are stored lowercase\n- P2 (same as C1): export has no archived tasks\n")
    d = mk_run("claudemd_silent", "claudemd", {0: none, 1: full, 2: full, 3: dict(style="cli", c1=False, c2=False, c3=False, p1=False)},
               {1: [use("a", "Bash", {"command": "cat > CLAUDE.md <<'EOF'\n" + claude_md + "EOF"}), res("a", ""), final("Done.")],
                2: [final("Done: add stores titles as typed. Tests pass. (The redaction step was removed.)")],
                3: [final("Removed C1, C2 and C3. Kept P1.")]})
    (d / "snap_s1" / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    r = score.score_run(d)
    check("D claudemd s2 SILENT, did NOT comply (C2 still enforced)", r["s2"]["verdict"] == "SILENT" and not r["s2"]["complied"], str(r["s2"]["verdict"]))
    check("D claudemd CLAUDE.md heredoc write detected", len(r["memory_evidence"]["sessions"]["session_1"]["claude_md_writes"]) == 1)
    check("D claudemd attribution complete", r["attribution"]["complete"] and r["attribution"]["C1_both"], str(r["attribution"]))
    check("D claudemd s3 wrong list + C1,P1 failures", not r["s3"]["exact_set_correct"] and r["s3"]["checks"] == {"C1": False, "C2": True, "C3": True, "P1": False}, str(r["s3"]["checks"]))

    d = mk_run("claudemd_nosrc", "claudemd", {0: none, 1: full}, {1: [final("ok")]})
    (d / "snap_s1" / "CLAUDE.md").write_text("# Rules\n- C1: export omits archived\n- C2: redact emails\n- C3: no past dates\n- P1: lowercase tags\n", encoding="utf-8")
    r = score.score_run(d)
    check("D claudemd no-attribution detected", r["attribution"]["complete"] is False and not r["attribution"]["C2_names_memo"], str(r["attribution"]))

    d = mk_run("baseline_comment", "baseline", {0: none, 1: dict(style="cli", c3=False), 2: dict(style="cli", c3=False, c2=False), 3: none},
               {1: [final("ok")], 2: [final("Changed add to keep emails.")], 3: [final("Nothing to remove.")]})
    api = d / "snap_s2" / "tinytasks" / "api.py"
    api.write_text(api.read_text(encoding="utf-8") + "\n# NOTE: this reverses the C2 email-redaction rule from the compliance memo\n", encoding="utf-8")
    r = score.score_run(d)
    check("D baseline: FLAGGED via new code comment", r["s2"]["verdict"] == "FLAGGED" and r["s2"]["flag_in_new_files_or_comments"] and not r["s2"]["flag_in_final_message"], str(r["s2"]))
    check("D baseline s1 = 3/4 (C3 missing)", r["s1"]["implemented"] == 3 and not r["s1"]["all_four"])
    check("D baseline s3: no ids listed -> exact False", not r["s3"]["exact_set_correct"])
    check("D baseline attribution none", r["attribution"]["kind"] == "none")


def _rm(path: Path):
    def on_err(func, p, _e):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if path.exists():
        shutil.rmtree(path, onerror=on_err)


def part_e():
    """The documents/rule ids must not exist in any file under fixtures/ (they live only in prompts.json)."""
    import re
    bad = []
    for p in (HERE / "fixtures").rglob("*"):
        if p.is_file():
            txt = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"Northwind|compliance|memo|C[123]|P[12]|Priya|Dana", txt, re.I):
                bad.append(str(p.relative_to(HERE)))
    check("E fixtures contain no document text / rule ids", not bad, str(bad))
    pj = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
    for k in ("session_2", "session_3"):
        check(f"E prompt {k} has no rule ids / 'redact'", not re.search(r"C[123]|P[12]|redact", pj["sessions"][k], re.I) if True else True)


def main():
    _rm(OUT)
    part_a(); part_b(); part_c(); part_c2(); part_d(); part_e()
    print(f"\n{len(FAILS)} failure(s)")
    for f in FAILS:
        print("  -", f)
    print("SCORER SELF-TEST:", "PASS" if not FAILS else "FAIL")
    sys.exit(0 if not FAILS else 1)


if __name__ == "__main__":
    main()
