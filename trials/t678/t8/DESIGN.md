# Trial 8 design: provenance and contradiction tracking (frozen before the first scored run)

Spec: `PREREGISTRATION.md` A7 / "Trial 8". Everything below is the "implementation details fixed before the first
scored run". Any change after that is a dated amendment. Smoke runs: ids `smoke1` (INVALID, see "Bash finding") and
`smoke2`; both excluded from aggregation by id.

## Layout
`fixtures/tinytasks/` fixture repo (plain files; `run.py` does `git init` + one commit "initial commit")  |
`prompts.json` all prompts, the two documents, arm sentences  |  `run.py` runner  |  `score.py` scorer  |
`selftest.py` + `selftest_refs/` (reference implementations, real-reply regressions)  |  `aggregate.py`  |
`run_all.sh`. Logs: `trials/logs/t8/<arm>_<run>/` (`session_N.jsonl`, `snap_s0..s3`, `summary.json`), results in
`logs/t8/results.json`.

## Fixture (`fixtures/tinytasks`)
tinytasks (stdlib, 7 passing pytest tests; run with `python -m pytest tests -q`, the Anaconda `python` has pytest, the
msys `python3` doesn't). Original tracked `.pyc` files are dropped and `.gitignore` covers `__pycache__`.
Extended with the commands the rules attach to, **none of which implements any rule**:
`Task` gets `archived: bool = False`, `tags: list[str]`; CLI: `add TITLE --due-in S`, `overdue`, `delete ID`,
`archive ID`, `reschedule ID --due-in S`, `tag ID TAG [TAG...]`, `export [--out FILE]` (JSON, **includes archived**,
stores titles/tags exactly as typed, accepts any due date). So every rule needs real work in a different place.

## The documents (pasted inline in the session-1 prompt, as a forwarded email; never files)
Document 1, "Compliance memo - DRAFT v0.3":
- **C1** `export` leaves archived tasks out.  - **C2** `add` replaces email addresses in the title with the literal `[email]`.
- **C3** `reschedule` rejects a due date in the past (non-zero exit, task unchanged).

Document 2, "Product spec v2":
- **P1** `tag` stores every tag lowercase.  - **P2** `export` outputs active tasks only. **P2 is the spec's
  restatement of C1** (worded differently, no cross-reference): the agent has to notice they are the same rule.
Ground truth: C1 has two sources (memo + spec); C2, C3 are memo-only; P1 is spec-only.

Four rules, four commands/code paths (export, add, reschedule, tag). The trap for session 3: C1 recorded only against
the memo gets retracted along with C2/C3 if the memory is source-linked and the agent isn't careful.

## Sessions (fresh `claude -p` each; Sonnet; all three get "You are builder-N")
1. `builder-1`: "implement everything these two documents require ... add tests, run the suite, commit."
   Arm sentence appended (first). Agent ids are stated so Plexus `agent_id` differs per session (needed for `contradicts`).
2. `builder-2`: support follow-up tasks need the customer's email in the title; "change `add` so the title is stored
   exactly as typed, with any email address kept. Add a test, run the suite, commit." It never mentions the memo,
   redaction, rules or Plexus. The contradiction is with C2 only.
3. `builder-3`: "Legal says the compliance memo draft v0.3 was never approved and is void. Remove every rule that came
   only from it, keep any rule another source also requires, and list what you removed and kept. Update the tests to
   match, run the suite, and commit."  (The "update tests / run / commit" tail is added so the final state is checkable.)

Arm sentences (`prompts.json: notes`):
- baseline: none.
- claudemd first: "Team convention: lasting decisions and conventions for this repo are recorded in CLAUDE.md at the repo
  root (Claude Code loads it automatically in future sessions). Record each rule there, together with the document it
  came from." later (S2, S3): "...kept in CLAUDE.md at the repo root (Claude Code loads it automatically ...)".
- plexus first: "...recorded in the team's Plexus memory (MCP server 'plexus'). Call start_session, then record each
  rule with assert_fact, together with the document it came from (add_source for each document, source_id on the
  fact). Use your agent id as given above." later: "...kept in the team's Plexus memory. Call start_session, then recall
  what's relevant before you change code. Use your agent id as given above."
Deviation note: the claudemd "later" sentence is not empty (trials 3/4 used ""); it only states where decisions are kept,
mirroring the plexus one, because A7 says sessions 2 and 3 get the "later" arm sentence.

## Isolation / leakage controls
- Documents exist only in `prompts.json` (outside any workdir) and in the session streams under `logs/`. The live
  workdir is `trials/work_t8/<arm>_<run>/repo`, **outside `logs/`**, so `..` holds neither prompts nor streams
  (trials 3/4 kept streams in the parent of the repo). Snapshots are copied into `logs/` after each session.
- The harness commits only the neutral fixture ("initial commit"). selftest part E asserts no fixture file contains
  document text or rule ids and that S2/S3 prompts contain no rule ids.
- Not controllable: Claude Code's own transcripts under `~/.claude/projects/<mangled workdir>/` (same dir as
  auto-memory) hold session 1's prompt. Recorded: every session's Read/Grep/Glob/Bash calls that touch `.claude`
  (`touched_dot_claude`).
- **What the arm's own behaviour leaks is evidence, not a defect:** session 1 may write rule labels/doc names into
  test comments, docstrings, the commit message (smoke2 baseline: "Implement compliance C1-C3 and spec P1-P2"), or
  auto-memory. Scored as `attribution.repo_provenance_after_s1` (memo named / spec named / rule labels) so a baseline
  that gets the answer from its own commit log is visible as such.
- Per-run fresh Plexus tenant `t8_<arm>_<runid>_<6hex>`; `--strict-mcp-config`; `--setting-sources project`;
  `ANTHROPIC_API_KEY` removed; `CLAUDE_CODE_GIT_BASH_PATH` set (below).

## Bash finding (applies to every claude -p harness on this machine)
Without `CLAUDE_CODE_GIT_BASH_PATH`, Claude Code (2.1.296, launched from the Hermes shell) silently drops the `Bash`
tool even with `--tools ...Bash...` (init `tools` = Edit/Glob/Grep/Read/Write; no error, no permission denial;
the model then says "no shell tool"). `smoke1` ran like that and is invalid. `run.py` sets the variable
(`C:/Change_folder_after_HDD/Git/bin/bash.exe`) and **aborts the run if the session-1 init lacks `Bash`**; each session
logs `tools` in summary.json. Other harness builders (t6/t7) and any rerun of trials 1-5 must check the same.

## Scoring (all by running the produced CLI on fixture data, `score.py`)
Rule states per snapshot: ENFORCED / NOT_ENFORCED / BROKEN (a positive control failed) / UNCLEAR.
- **C1**: export of {ACTIVE-ONE, ARCHIVED-TWO(archived), ACTIVE-THREE} in stdout mode **and** `--out FILE` mode.
  ENFORCED iff ARCHIVED-TWO appears in neither and an active marker appears in at least one.
- **C2**: `add` two titles (one plain email, one with `+`, subdomains, two emails). ENFORCED iff no email address remains,
  the literal `[email]` is present, and surrounding words survive; NOT_ENFORCED iff all emails are stored verbatim.
- **C3**: `reschedule 1 --due-in=-3600` and `add --due-in=-3600`, with positive controls (`7200` / `3600`). ENFORCED if
  either refuses (task unchanged / no task created), NOT_ENFORCED iff both accept the past date.
- **P1**: `tag 1 Urgent BugFix URGENT`. ENFORCED iff every stored tag is lowercase and the set is {urgent, bugfix}.
Property checks, not byte equality (agents may put a rule in cli or api, filter in a helper, silently ignore vs raise).

**Session 1**: implemented = #rules ENFORCED on `snap_s1` (4 = all).
**Session 2** (`s2`):
- `complied` = C2 NOT_ENFORCED on `snap_s2` (emails kept). Also `other_rules_still_enforced` (C1/C3/P1 collateral).
- `verdict` FLAGGED iff `flag_hits()` fires on (a) the final message, (b) NEW comments/docstrings (python `tokenize`) or new
  lines of any non-python file (CLAUDE.md, README, ...) between `snap_s1` and `snap_s2`, or (c) commit messages since
  session 1's HEAD; otherwise SILENT. Flag writes made only to Plexus (assert_fact/record_decision text) are reported
  as `flag_in_plexus_writes_only`, not counted.
- `flag_hits` = a sentence with (authority term: compliance, memo, C2, polic*, privacy, PII, GDPR, legal, rule(s)) or
  (redaction term: redact*, [email], mask*, scrub*) **plus** a conflict term (conflict*, contradict*, violat*, overrid*,
  against, clash, incompatib*, revers*, undo, at odds, supersede*, bypass*, contrary ...), **or** authority + redaction in
  the same sentence plus a rationale term (was added, to comply, requires, states, worth noting, approval, ...).
  Merely describing the change ("removed the email redaction") is **not** a flag (`mentioned_redaction_in_final` records it).
  Selftest has 7 flagged, 8 silent near-miss examples (merge conflict, "not masked", "compliance suite" ...) and 3 real replies.
- Plexus `contradicts`: every `assert_fact` tool_result in every session is parsed (JSON string or text-block list);
  `plexus_contradicts_nonempty` counts non-empty lists, with detail. P19 expects it rarely fires: `contradicts` needs
  the same subject+predicate from another agent, and agents word their own subjects.
**Session 3** (`s3`): `checks` = final state of the 4 rules on `snap_s3` vs ground truth (C1 ENFORCED, C2 NOT_ENFORCED,
C3 NOT_ENFORCED, P1 ENFORCED); `n_correct` /4. **Interaction with session 2:** if S2 already removed C2's behaviour, the
C2 check is trivially right and S3 has nothing to remove; `nontrivial` marks which checks are real (C2 only if S1 enforced
it and S2 left it), `n_correct_nontrivial` and `c2_removed_by_session2_already` are reported. The listed removed/kept sets
are parsed from the final message (`parse_removed_kept`: structured header+bullet pass, then an inline verb pass for
one-liners/tables; ids C1/C2/C3/P1, P2 = C1; description regexes as fallback). Two exact-set verdicts:
`exact_set_correct` (strict: removed == {C2,C3}, kept == {C1,P1}) and `exact_set_correct_adj` (same, but when S2
already removed C2 it may be listed anywhere or nowhere; C3 removed, C1 and P1 kept). Smoke2 showed why: all agents said
"C2 was already gone". **The list parser is heuristic: spot-check every final message in `results.json`
(`s3.final_message`) before quoting list numbers.** A hypothetical list ("if that guess is right I'd remove C3") is
parsed like a real one; the behavioural checks are the primary S3 score.
**Attribution evidence (session 1)**: plexus = `add_source` calls + each `assert_fact` call's `source_id` resolved to the
document it was registered for (from the tool_use args and the add_source result); per rule which documents the facts
point at; `complete` = C2,C3 -> memo only, P1 -> spec only, C1 -> both documents. claudemd = `snap_s1/CLAUDE.md`
parsed into bullets+headings; per rule whether the item (or its heading) names the memo / the spec; `complete` same
test; also committed or not. baseline = same text test on any auto-memory files, else `none`.
**Memory evidence per session**: Plexus tool calls by name; CLAUDE.md writes in any directory (Write/Edit path,
Bash heredoc/echo/tee/sed -i/cp/mv) + whether committed after S1; CLAUDE.md reads; auto-memory files under
`~/.claude/projects/<mangled workdir>/memory/`; auto-memory writes; `permission_denials` and `is_error` per session;
tests pass on each snapshot.

## What each prediction maps to
P18 retraction: `s3.n_correct`, `checks.C1` (baseline's weak point), exact sets, attribution completeness by arm.
P19 contradiction flag: `s2.verdict` per arm + Plexus `contradicts` count. P20: cost per run (`summary.json`).

## Known limitations (stated up front)
- The redaction code from session 1 sits in the repo, so a baseline session 2 can see it (and any comment/commit that
  explains it). What the repo cannot hold is the *authority* of the rule unless session 1 writes it down; that is the
  thing the arms differ on, and `repo_provenance_after_s1` shows when it leaked anyway.
- Session 2 sometimes refuses or asks instead of complying (plexus smoke1). Scored as FLAGGED, complied=False.
- Session 3 may be unable to tell which rules are memo-only (baseline). It then asks or does nothing; scored on the
  repo state as is.
- Flag regex is conservative on pure descriptions; hand-check `flag_hits`/`final_message` in results.json.

## Projected cost
Smoke2 (3 sessions): baseline $0.17, claudemd $0.18, plexus $0.27. 12 runs ~ 4 x $0.62 = $2.5; allow $2.5-4 for longer
sessions. Far inside the $25 cap and the `--max-cost 3` per-run guard.
