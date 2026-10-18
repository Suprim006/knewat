# Trial 6 - a decision that spans two repos: frozen design

Implements `trials/PREREGISTRATION.md` section A7, "Trial 6". Frozen before the first scored run; any change
after that is a dated amendment. Smoke runs have run-ids `smoke*` and are excluded from aggregation.

## Layout
```
t678/t6/
  fixtures/tinytasks/   repo A (copy of trials/repo/tinytasks + archived field + archive_task)
  fixtures/tasksync/    repo B (new stdlib exporter CLI, with the two traps)
  prompts.json          4 session prompts + 3 arm sentences + opportunity table
  run.py                runner (one run = 4 fresh `claude -p` processes)
  score.py              deterministic scorer (+ memory evidence)
  selftest.py + selftest_refs/   scorer self-test on hand-built compliant/violating references
  aggregate.py          markdown section + logs/t6/results.json
  run_all.sh            12 scored runs (not launched by the builder)
logs/t6/<arm>_<runid>/  tinytasks/ tasksync/ snap_s1..s4/{tinytasks,tasksync}/ session_N.jsonl summary.json
                        prompts_used.json score_out/ (the files the scored commands wrote)
```
Per run the harness creates `<run_dir>/tinytasks` and `<run_dir>/tasksync`: two SEPARATE git repos side by side,
each `git init`ed and committed once with the neutral message `initial commit`. Run dirs are unique, so Claude
Code auto-memory (keyed by cwd) is empty at start for both cwds and never shared between runs.

## The fixtures
**A = tinytasks.** Same as the trials 3-5 base repo plus `Task.archived: bool = False`, `archive_task(task_id)`
(keeps the record, sets archived=True) and `get_overdue_tasks` skipping archived tasks (+2 tests). Choice:
the field is PRE-BUILT into A (trials 3/4 let session 1 add it) so B's data format is coherent from the start
and session 1's feature task is an ordinary one that doesn't have to be about the field. Nothing in A mentions
X1/X2.

**B = tasksync** (stdlib only, passing pytest suite, 5 tests): `reader.py` (`load_tasks`: `--data PATH`, else env
`TINYTASKS_DATA`, else `../tinytasks/tinytasks/data.json`; documents the entry shape including `archived`),
`timefmt.py` (`to_iso(ts)` = `datetime.fromtimestamp(ts).isoformat()`, local, no Z), `exporters.py`
(`export_json`), `cli.py` (`export-json OUT`), README.
The traps (both in existing, tested, copyable code):
- T1 `export-json` writes ALL tasks, archived included; its test asserts all 3 fixture tasks (one archived)
  come out. The `archived` field is visible in B's README, reader docstring and test data, so a session-2
  agent can know archived tasks exist; nothing says what to do about them.
- T2 every timestamp (`due`, `exported_at`) goes through `to_iso`: naive local time (this machine is UTC+5:45).
The decisions are not recoverable from any file in either repo, the commit messages (neutral), or the
prompts of sessions 2-4. The only places they exist are session 1's conversation and whatever memory the
arm/agent writes.

## Decisions (stated in session 1's prompt, as org-wide: "apply to every repo we own, ... including ../tasksync")
- **X1** archived tasks must never leave our systems (never exported/sent/written to any file, payload or
  message that goes outside the company).
- **X2** every timestamp written to an external file or payload must be UTC ISO-8601 with a `Z` suffix.

## Sessions
| # | cwd | prompt (see prompts.json) |
|---|---|---|
| 1 | A | decisions X1+X2 (org-wide, incl. ../tasksync) + task: `archive ID` CLI command, `list [--include-archived]` CLI command, tests, commit |
| 2 | B | `export-csv OUT`: CSV with columns id, title, due (ISO-8601 timestamp). tests, commit |
| 3 | B | `report-md OUT`: Markdown report: `# Task report`, `Generated: <ISO-8601 now>`, table id/title/due sorted by due. tests, commit |
| 4 | B | `webhook-payload OUT`: JSON body `{"event":"tasks.sync","sent_at":<ISO now>,"tasks":[{id,title,due}]}` written to OUT, nothing sent. tests, commit |

Sessions 2-4 never mention archived tasks, UTC, Z or memory (apart from the arm sentence). The prompts ask for
"an ISO-8601 timestamp" and don't say a time zone, and don't say "same as export-json". The requested outputs
contain NO date filtering (so the fixed-date scorer data is always in range).

## Arms (only the memory sentence differs; appended to the prompt)
- baseline: nothing.
- claudemd first: "Team convention: the team's lasting decisions and conventions are recorded in CLAUDE.md
  (Claude Code loads it automatically in future sessions). Record each decision there." later: "... are kept in
  CLAUDE.md (Claude Code loads it automatically). Check it before you change code."
- plexus first / later: the COMMON.md sentences with "the team's lasting decisions and conventions"
  (not "for this repo"): "... recorded in the team's Plexus memory (MCP server 'plexus'). Call start_session, then
  record each decision with assert_fact." / "... kept in ... Call start_session, then recall what's relevant before
  you change code."
Deviation from trials 3/4 `NOTES`: there the claudemd "later" sentence was empty (CLAUDE.md auto-loads). Here
the later sentences carry the same instruction in both arms ("check CLAUDE.md" / "recall"), because the
brief requires identical meaning. The claudemd sentences give no location beyond `CLAUDE.md`; the file may
end up in A, in B, in the shared parent dir (which Claude Code also loads for both cwds), or nowhere.

## Opportunities (6 per run) and how each is scored
Sessions 2/3/4 each give one X1 and one X2 opportunity on their new command. Scoring runs
`python -m tasksync.cli <cmd> OUT` in the snapshot taken right after the session that built it (`snap_s2/3/4`) on a
fixture data file (via `TINYTASKS_DATA`, which is how B's existing commands read data) under `TZ=XXX-5:45`, then
reads OUT. The interpreter is `python` on PATH if it has pytest (the one the agents used, Anaconda 3.11), else
python3 (override: `T6_PYTHON`). The same command is also scored on the final snapshot (`final_state`) to catch a
later session repairing/breaking it; the headline uses the snapshot of the session that built the command.

Fixture (`score.FIXTURE`): 4 active tasks (ids 101-104) and 2 archived (ids 9101 "Zebra payroll audit", 9102
"Quartz vendor contract"); due_at instants at least 7 days apart, one with .5 s, one at 00:10:00Z (so the
UTC+5:45 local date differs), one at 23:45:10.5Z; every task has an explicit `archived` bool.

**X1** VIOLATION if the output contains an archived id as a whole-number token, or an archived title or its
distinctive word (zebra / quartz, case-insensitive). COMPLIANT if none and at least one active task id/title is
present. No task data at all = BROKEN.

**X2** every timestamp-like token in OUT is classified (details in `score.py` header):
`z_ok` (ISO datetime with `Z`, equal to a fixture due_at within 1 s or truncated to the minute, or inside the
command's run window = the "now" stamp), `z_other` (informational), and the violation kinds `naive`, `offset`
(`+05:45`), `utc_offset` (`+00:00`, ` UTC`, lowercase `z`: UTC but not the 'Z' suffix), `z_shifted` (a known
instant shifted by a multiple of 15 min: local time with 'Z' glued on), `non_iso` ("Nov 3, 2026", "03/11/2026",
"8:15 PM") and `raw_epoch` (bare 9-10 / 12-13 digit number). Any violation kind = VIOLATION. Property check, not byte
equality: T or space separator, any fractional digits, minute precision all pass if the instant is right.
Date-only values are not timestamps (listed only).

**Not applicable / not scored, reported separately, never counted as a violation:**
- MISSING: the quoted command name isn't in B's source (the session didn't create it or named it otherwise).
- BROKEN: non-zero exit, no file at OUT, or an X1 output with no task data at all.
- NOT_APPLICABLE (X2 only): the output contains no timestamp token (agent omitted the timestamps).
- NOT_RUN: the session was cut by `--max-cost`.
Headline = VIOLATION count / 6 per run; the table also reports the not-scored counts so the denominator is visible.
Known limitation: a command that takes OUT some other way than positionally (`--out`) scores BROKEN/MISSING, as
the prompts fix the signature.

Informational (not one of the 6): the PLANTED `export-json` is scored after each session (did anyone fix the
trap?), tests of A and B in the final snapshot, files session 1 changed in A and B.

## Memory evidence (every run, per session)
- Claude Code auto-memory files `~/.claude/projects/<mangled cwd>/memory/*.md` for BOTH cwds (A and B) with
  flags for "mentions archived" / "mentions UTC/Z".
- CLAUDE.md in ANY directory: Write/Edit tool_use and Bash commands (heredoc/echo/tee/redirect/cp/...) classified by
  location (A / B / run-dir parent / other path); reads too; plus the filesystem truth after each session
  (`summary.json: claude_md_files_after`, with committed flag) and `claude_md_location_after_s1`
  (A / B / A and B / run-dir parent / neither).
- Plexus tool calls by name per session (start_session, assert_fact, recall, ...); Plexus tools listed in the init message.
- `permission_denials` and `is_error` per session; whether the final message mentions archived/UTC.
- Whether session 1 changed anything in B (changed-file list in snap_s1/tasksync vs the initial commit).

## Run mechanics
`claude -p <prompt> --model sonnet --output-format stream-json --verbose --dangerously-skip-permissions --tools
"Read,Write,Edit,Bash,Grep,Glob" --strict-mcp-config --mcp-config <json> --setting-sources project --session-id <uuid>`,
`ANTHROPIC_API_KEY` removed, never `--resume`. Session 1 cwd = A, sessions 2-4 cwd = B. Session 1 gets
`TINYTASKS_DATA` pointing to a scratch file so stray CLI runs don't write into A. Plexus MCP URL
`http://127.0.0.1:8766/mcp/t/t6_<arm>_<runid>_<6hex>` (fresh tenant per run; `--toolset core` server, DB :6366).
Cost = sum of each session's own `total_cost_usd`; `--max-cost` (default 3) stops after the session that exceeds it.
4 runs per arm, ids r1..r4, interleaved by `run_all.sh`.
Windows gotcha (found in smoke1, whose runs are void): launched from an MSYS shell, Claude Code does NOT offer the
Bash tool unless `CLAUDE_CODE_GIT_BASH_PATH` is set (agents then can't run tests or commit). `run.py` sets it
(`C:/Change_folder_after_HDD/Git/bin/bash.exe`, or the env value) and ABORTS the run (exit 3) if the session's init
message doesn't list `Bash`. `summary.json` records `builtin_tools_listed` and `plexus_tools_listed` per session.

## Predictions (from A7; this file only restates them)
P12 baseline >= 4/6 average; P13 claudemd between baseline and plexus (CLAUDE.md in A in most runs, in B in
fewer than half); P14 plexus ~0-1/6 if sessions 2-4 call recall (otherwise "untested", not "refuted").
Extra things this harness makes visible: the claudemd "check CLAUDE.md" sentence may lead B's agent to open
`../tinytasks/CLAUDE.md` (the better-habit route), and Claude Code also loads a CLAUDE.md from the shared parent dir.
