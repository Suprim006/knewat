# Trial 7 design (frozen before the first scored run)

Trial 7 of `PREREGISTRATION.md` A7: **memory shared between different agents running in parallel on git
worktrees, plus a non-LLM tool (ci-bot)**. Everything here is fixed before the first scored run; later changes
need a dated amendment. Files: `fixtures/tinytasks/` (source repo), `prompts.json`, `run.py`, `plexus_mcp.py`
(stdlib MCP client, adapted from `plexus-repo-workflow/scripts/plexus_mcp.py`), `score.py`, `selftest.py` +
`selftest_refs/`, `aggregate.py`, `run_all.sh`. Logs: `trials/logs/t7/<arm>_<runid>/`.

## Fixture
`fixtures/tinytasks` = `trials/repo/tinytasks` (`add`, `overdue`, `delete`; `due_at` = Unix seconds; JSON
storage via `TINYTASKS_DATA`) plus one file: `tinytasks/queries.py` with `tasks_due_before(cutoff)` (and a test).
Nothing in the code, README, docstrings or the harness's git history states Y1 or Y2:
- `create_task` / `add` write exact-second due dates (the trap for Y1: the only pattern B can copy is unrounded).
- `get_overdue_tasks()` has no deprecation marker, a normal docstring, and is the obvious function for anything
  "overdue" (the `overdue` command calls it). `tasks_due_before` lives in a separate module, so a grep for
  "overdue" finds only the deprecated one.
- Tests: 4 pytest tests (`python -m pytest`, anaconda `python` 3.11 has pytest; msys `python3` does not and is
  only used for the harness/scorer).
Per run the harness copies the fixture to `<run>/tinytasks`, `git init -b main`, one commit "initial import"
(neutral message), then `git worktree add -b feat-a <run>/wt_a main` and `git worktree add -b feat-b <run>/wt_b main`
(same commit). The harness never merges `feat-a`.

## Sequence (all sessions are fresh `claude -p` processes, never `--resume`)
| Step | Who | Model | cwd | What |
|---|---|---|---|---|
| A | `planner-builder` | sonnet | `wt_a` | feature + Y1, commits on feat-a, "goes to review, don't merge" |
| B1 | `builder-2` | haiku | `wt_b` | two features, each touches Y1 (2 opportunities), commits on feat-b |
| ci-bot | plain Python | none | n/a | records Y2 (see below) |
| B2 | `builder-2` | haiku | `wt_b` | one feature where calling the deprecated function is the shortcut (1 opportunity) |

Flags per session: `--model <sonnet|haiku> --output-format stream-json --verbose --dangerously-skip-permissions
--tools "Read,Write,Edit,Bash,Grep,Glob" --strict-mcp-config --mcp-config <json> --setting-sources project
--session-id <uuid>`, `ANTHROPIC_API_KEY` removed, `TINYTASKS_DATA` pointed at a scratch file outside the repos,
`PYTHONDONTWRITEBYTECODE=1`. Models resolve to `claude-sonnet-5-5` / `claude-haiku-5-5` (recorded from the init
message). Prompts are argv (< 8k). Cost per session = `total_cost_usd` of that session's result; summed. Cap:
`--max-cost` (default 3 per run), checked after each session. No ancestor directory of a run holds a CLAUDE.md.

Plexus arm: fresh tenant `t7_plexus_<runid>_<6hex>`, MCP URL `<plexus-url>/mcp/t/<tenant>`; the other arms get an
empty `--mcp-config`. Agent ids are in the prompt of every arm ("You are the coding agent 'planner-builder'") and
repeated in the plexus sentence so the agent passes the right `agent_id` to Plexus.

## Decisions
**Y1 (stated only to A, by "the tech lead, Maya"):** *any due date new code writes is rounded down to a whole
minute: the stored `due_at` of a task written/changed by a new command is a multiple of 60 (still Unix seconds,
same field). Existing `create_task` and `add` stay exactly as they are (sync service depends on their exact-second
behaviour).* A's task: `snooze ID MINUTES` + `snooze_task(task_id, minutes)`, tests, commit on feat-a. A's own
`snooze` is scored as a sanity check (`A_snooze_followed_Y1`), not as an opportunity.

**Y2 (recorded only by ci-bot):** *`get_overdue_tasks()` in `tinytasks/api.py` is deprecated and slated for removal.
New code must not call it; use `tinytasks.queries.tasks_due_before(cutoff)` instead (cutoff = current Unix time in
seconds). The existing `overdue` command keeps using it until it is migrated.*
- plexus arm: ci-bot connects over MCP HTTP as agent `ci-bot`, `add_source(kind='tool', title='CI deprecation check
  (tinytasks)', text=<value>)`, then `assert_fact(subject='tinytasks get_overdue_tasks', predicate='status',
  value=<text>, scope='global', source_id=<id>)`.
- baseline / claudemd: ci-bot appends a dated line with the same text to `<run>/tinytasks/CI_NOTES.md`, i.e. the
  MAIN checkout (not a worktree), created if missing, never `git add`ed. Nothing auto-loads it; B can only find it
  by looking outside its worktree (`git worktree list`, `find ..`).
Why B can't just read it from the code: A's work is on an unmerged branch; B branched from `main` before A started.

## Opportunities (3 per run) and how each is scored
Everything is judged on the code the agent left in `snap_B1` / `snap_B2` (copy of `wt_b` after the session,
`.git` stripped), never on prose. Scorer = `score.py`, deterministic, stdlib.

| # | Session | Command (given in the prompt) | Rule | Check |
|---|---|---|---|---|
| 1 | B1 | `quick-add TITLE` (due 24 h from now) | Y1 | run on empty data, fake clock, read stored `due_at` |
| 2 | B1 | `postpone ID HOURS` (due date back by HOURS) | Y1 | run on fixture task `due_at = T0 + 1234.5`, `postpone 1 2` |
| 3 | B2 | `status` (prints `<N> tasks, <M> overdue`) | Y2 | AST/call-graph delta B1 -> B2, plus behaviour check |

**Y1 checks** run the CLI as `python3 -c <launcher>` where the launcher sets `time.time = lambda: 1_800_000_037.5`
(not on a minute boundary) before importing `tinytasks`, then `runpy`s `tinytasks.cli`. Verdict:
- COMPLIANT: stored `due_at` is a multiple of 60 (within 1 ms; floor, ceil or nearest all pass) AND within +-61 s of
  an expected value (fake-clock based, or real-clock based for agents using `datetime.now()`; for `postpone` also
  `old due_at + 7200`).
- VIOLATION: stored `due_at` is an epoch-seconds value (> 1e9) that is not a multiple of 60.
- UNCLEAR: a multiple of 60 but far from every expected value, or not epoch-seconds (e.g. a minutes unit).
- BROKEN: command missing, crashes, or stores nothing.

**Y2 check** (`score_y2_status`): collect every reference (Name load / Attribute) in `tinytasks/**/*.py` (tests
excluded) as `(enclosing function, name)`, resolving `from x import y as z` and `g = y` aliases. Compare
`snap_B2` against `snap_B1`:
- VIOLATION if references to `get_overdue_tasks` increased, or references to a package function (other than `main`)
  that existed after B1 and transitively reaches `get_overdue_tasks` increased (call graph by name). A pure refactor
  that moves the existing `overdue` branch into a new function leaves the total unchanged and is NOT a violation;
  a new wrapper created in B2 contains its own reference and is counted directly.
- else COMPLIANT if `status` works (fixture with 5 tasks, 2 overdue -> output matches `5 tasks, 2 overdue`);
- else BROKEN (no new reference but the feature doesn't work, so the shortcut was not tested).
Reported as descriptive extras: `new_refs_to_tasks_due_before`, `final_state` of the two Y1 commands on `snap_B2`.
Headline = VIOLATION count over the 3 opportunities (Y1 /2, Y2 /1), BROKEN/UNCLEAR reported separately.

## Arm sentences (appended to the prompt; baseline gets nothing)
- claudemd, A: "Team convention: lasting decisions and conventions for this repo are recorded in CLAUDE.md at the repo
  root (Claude Code loads it automatically in future sessions)."
- claudemd, B (the "later" variant): "Team convention: the team's lasting decisions and conventions for this repo are
  kept in CLAUDE.md at the repo root (Claude Code loads it automatically). Check it for what's relevant before you
  change code."
- plexus, A: the COMMON.md first-session sentence + "Your agent_id for Plexus calls is 'planner-builder'."
- plexus, B: the COMMON.md later-session sentence + "Your agent_id for Plexus calls is 'builder-2'."
Deviation from trials 3/4: there the claudemd "later" sentence was empty (CLAUDE.md autoloads). Here B gets a
sentence of equal meaning to Plexus's "recall before you change code", as the A7 brief says both arms get the
sentence, so Plexus's advantage can't come from a better instruction.

## Memory evidence (`score.py` -> `memory_evidence`)
- Claude Code auto-memory: the `memory_paths.auto` directory each session reports in its init message (the dir it
  actually loads), `~/.claude/projects/*` dirs belonging to the run and their `memory/*` files after each session,
  and whether A and B1 loaded the same dir. Mangled path of main / wt_a / wt_b recorded too.
- CLAUDE.md: Write/Edit tool calls and Bash writes (redirect, tee, sed -i, cp/mv, python open('w'); heredoc bodies
  and `2>/dev/null` ignored) in any directory; whether it exists on disk in each snapshot, is tracked on feat-a /
  feat-b / main (`git ls-tree`), and whether it reached the main checkout.
- Plexus tool calls by name and `agent_id` per session (expected `planner-builder` / `builder-2`; ci-bot call
  results in `summary.ci_bot`), whether recall results contained Y1 / Y2 text, plus an end-of-run audit dump
  (`recall` as `harness-audit`) with fact authors.
- Leak paths: B touching `CI_NOTES`; B's tool inputs mentioning `wt_a` / `feat-a`; `git worktree|branch|log --all`
  commands; Y1/Y2 text appearing in B's tool results; B reading CLAUDE.md.
- `permission_denials`, `is_error`, return code, cost, turns per session; git log / status of each branch.

## Smoke findings that shaped the design (smoke ids `smoke1`, `smoke2`, excluded from results)
1. **Claude Code shares auto-memory across worktrees of one repo.** The dir is keyed by the MAIN checkout root
   (`...-tinytasks`), not the worktree: A (wt_a) and B (wt_b) report the same `memory_paths.auto`. A baseline A that
   writes auto-memory therefore reaches B (baseline_smoke1: A wrote `whole-minute-due-dates.md`, B followed Y1).
   Session transcripts (`*.jsonl`) are still stored per worktree path. This is a native-memory finding for P15.
2. **claudemd B hunts for CLAUDE.md.** Told to check CLAUDE.md, B finds none in wt_b and in 1 of 2 smoke runs looked
   at `../wt_a/CLAUDE.md` and `git log --all`. Recorded as `peeked_at_A`; it is allowed behaviour, reported, not
   hidden.
3. Detector false positives fixed before the freeze (`cat CLAUDE.md 2>/dev/null`; `CLAUDE.md` text inside a
   heredoc body) and covered in `selftest.py`.

## Scorer self-test
`python3 selftest.py` builds 14 synthetic runs from hand-built references in `selftest_refs/` (compliant, violating,
datetime/round-to-nearest variant, mixed, minutes-unit, broken, aliased/attribute/wrapper calls to the deprecated
function, a pure refactor, status missing/wrong) and checks the verdict for each opportunity, the A-snooze sanity
check, `judge_due` edge cases, the memory-evidence detectors on a synthetic stream, and the Bash write detector.
Must print `PASS` (currently 71/71). `run_all.sh` refuses to start if it fails.

## Known limits
- Different "tools" = a second model + a non-LLM bot, not a second agent product (no second LLM harness installed).
- B can reach A's unmerged branch by git (`git log --all`). That is outside "not recoverable from the code B
  sees" only if B goes looking; it is flagged, not prevented (preventing it would be unnatural for worktrees).
- Y1 rounding direction is not constrained (floor/ceil/nearest all pass); `postpone` semantics (relative to current
  `due_at`) are not enforced beyond the +-61 s window and "other task untouched" (reported).
- Y2 call graph is name-based and static; `getattr`/dynamic access isn't seen.
- Fake clock only patches `time.time`; `datetime.now()` users are matched against real-clock windows instead.
