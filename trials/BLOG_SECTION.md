<!--
PLACEMENT (for the owner, not part of the post): put this section right after the first-screen bullets and before
"Three agents, one project, and no way to ask why". Hidden `src:` comments follow the convention in docs/BLOG_DRAFT.md.
Every number comes from trials/FINDINGS.md, trials/RESULTS_T678.md or trials/PREREGISTRATION.md.

OPTIONAL fourth bullet for the first screen (same sources):
- In three everyday team workflows (a rule set in another repo, parallel worktrees with an unmerged branch, retracting a void source), plain Claude Code broke the team's rules 24 of 24 and 9 of 12 times. With Plexus it broke 0 of 24 and 0 of 12. n = 4 runs per arm, small synthetic repos.
-->

## Where shared memory actually helps: three everyday workflows

My first five trials showed that plain Claude Code is not memoryless (in 4 of 4 baseline runs it saved the team's rules without being told to) and that a committed `CLAUDE.md` ties Plexus when the work stays in one repo. So I looked for cases where a file cannot reach the next agent. Each trial has three arms that differ by one sentence: plain Claude Code, Claude Code told to keep lasting decisions in `CLAUDE.md`, and Claude Code with Plexus. Every step is a separate `claude -p` session. A script scores the result by running the code the agent wrote, with no LLM judge. Each arm got 4 runs, and I wrote my predictions down before any scored run.

<!-- src: 4 of 4 -> trials/FINDINGS.md:22-30; ties in one repo -> FINDINGS.md:32-62; arms, sessions, scoring, 4 runs, predictions first -> PREREGISTRATION.md:113-142 (A7) -->

### Trial 6: a decision made in repo A, work done in repo B

Two repos, `tinytasks` and `tasksync`. In the first session, in `tinytasks`, the agent is told two org-wide rules that apply to `../tasksync` too: archived tasks never leave our systems, and every external timestamp is UTC ISO-8601 with a `Z`. Nothing in `tasksync` shows either rule, and its existing exporter breaks both. Three later sessions in `tasksync` add a CSV export, a Markdown report and a webhook payload without mentioning the rules. That is 24 chances per arm.

Plain Claude Code broke the rules 24 of 24 times, and so did the `CLAUDE.md` arm. It wrote and committed the decisions in `tinytasks/CLAUDE.md` in 4 of 4 runs, and the later sessions looked for a `CLAUDE.md` only in `tasksync`. The Plexus sessions called `recall` every time (12 of 12) and followed both rules on all 24 chances. Writing the note into each repo would have worked, but no agent did that unprompted. I had predicted the `CLAUDE.md` arm would beat plain Claude Code. It did not.

<!-- src: design -> t678/t6/DESIGN.md:44-59; 24/24, 24/24, 0/24 -> RESULTS_T678.md:22-24; CLAUDE.md in A 4/4, B 0/4, P13 refuted -> PREREGISTRATION.md:257-258; recall 12/12 -> :259; file-based fix -> FINDINGS.md:128-129 -->

### Trial 7: parallel worktrees, an unmerged branch and a bot

Two git worktrees from one commit. Agent A (Sonnet) is told that due dates new code writes are rounded down to a whole minute, and commits on a branch that stays unmerged. Agent B (a different agent id and model, Haiku) builds two features in the other worktree that touch due dates. Then `ci-bot`, a plain Python script with no LLM, records that `get_overdue_tasks()` is deprecated. With Plexus it writes to the shared memory. Otherwise it appends a line to an uncommitted `CI_NOTES.md`, as a team without Plexus would. That is 12 chances per arm.

Plain Claude Code broke the rules 9 of 12 times, the `CLAUDE.md` arm 8 of 12, Plexus 0. Native memory helped some: Claude Code shares auto-memory across worktrees of one repo (12 of 12 runs), and in the one baseline run where A wrote a note, B followed it. A's `CLAUDE.md` sat on the unmerged branch, and B went looking there in 3 of 4 runs. Nobody read the bot's note (0 of 16 sessions), and B called the deprecated function in 7 of 8 runs in these two arms.

<!-- src: design -> t678/t7/DESIGN.md:23-58; 9/12, 8/12, 0/12 -> RESULTS_T678.md:70-72; auto-memory shared, r3 -> FINDINGS.md:133-134; B hunted 3/4, CI_NOTES 0/16, 7/8 -> FINDINGS.md:135-138 -->

### Trial 8: provenance, and retracting a void memo

One repo, three sessions. The agent gets a compliance memo (rules C1 to C3) and a product spec (P1, and a rewording of C1), and records each rule with its source. Later it is told the memo is void: remove every rule that came only from it, and keep any rule another source also requires. The right answer is to remove C2 and C3 and keep C1 and P1.

This was a tie. The `CLAUDE.md` arm and Plexus both kept C1 and P1 and removed C3 in 4 of 4 runs. Plain Claude Code removed C3 in 0 of 4, because every run refused to guess and changed nothing. That is a safe no-op, not a wrong retraction.

The tie hid a gap. `assert_fact` took one `source_id`, so agents linked C1 only to the memo and wrote "also product P2" in its text. Session 3 got C1 right by reading that text, and no agent called `quarantine_source`. Quarantining the memo would have hidden C1 wrongly. That was my bug, not the agents'.

I made `assert_fact` take `source_ids` and rewrote the tool descriptions, then re-ran the Plexus arm on the final code (4 runs). C1 was linked to both documents in 4 of 4 runs (before: 0). Session 3 retracted through the graph in 4 of 4 (before: 0), and each call returned the right answer: C2 and C3 hidden or forgotten, C1 kept as corroborated by the spec. I had predicted at most 2 of 4 would use those tools.

<!-- src: design -> t678/t8/DESIGN.md:22-43; tie, baseline no-op -> FINDINGS.md:116-119, 142-145; single source_id gap -> FINDINGS.md:146-150; fix and re-run -> FINDINGS.md:158-166, PREREGISTRATION.md:293-323 (P23 at :308) -->

### Results

| | Plain Claude Code | + `CLAUDE.md` | + Plexus |
|---|---|---|---|
| 6: rule broken, of 24 chances | 24 | 24 | 0 |
| 7: rule broken, of 12 | 9 | 8 | 0 |
| 8: C1 and P1 kept (of 8), C3 removed (of 4) | 8, 0 | 8, 4 | 8, 4 |
| Cost per run, trials 6 / 7 / 8 | $0.26 / $0.07 / $0.16 | $0.28 / $0.07 / $0.18 | $0.36 / $0.08 / $0.25 |

<!-- src: FINDINGS.md:112-116; RESULTS_T678.md:22-24, 70-72, 145-148 -->

### What this does and doesn't show

Each arm had 4 runs, the repos are small and synthetic, and I designed these trials after seeing trials 1 to 5, so they are exploratory. Plain Claude Code's auto-memory and a committed `CLAUDE.md` tie Plexus wherever a file reaches the next agent: one repo (0 of 24 violations in every arm), a fresh clone with a committed `CLAUDE.md` (0 of 24), and trial 8. Plexus wins where nothing reaches the next agent. A better habit could close trial 6, and I measured default behavior.

Trials 6 to 8 ran on the `trials-int` build, before later cleanup. Recall returned the needed facts in every Plexus session (12 of 12, 8 of 8), so I did not re-run them. Only the trial 8 re-run used the final code. Plexus cost 30%, 22% and 39% more per run than the `CLAUDE.md` arm. The 36 scored runs cost $6.77, smoke runs $3.64 more, and the re-run $0.94.

<!-- src: n=4, exploratory -> PREREGISTRATION.md:113-118; ties -> FINDINGS.md:32-62, 171-174; better habit -> :128-129; second tool -> PREREGISTRATION.md:181-182; builds -> FINDINGS.md:3-14; recall 12/12, 8/8 -> PREREGISTRATION.md:286-291; +30%, +22%, +39% -> :275; $6.77, $3.64 -> FINDINGS.md:110; $0.94 -> :158 -->
