# Findings: Plexus vs Claude Code in everyday workflows

> **Status (2026-10-18): current.** The owner judged that the changes after these runs (the cleanup, removed
> off-by-default switches, lexical fusion off) don't affect what these trials measure, so they weren't re-run.
> The Plexus build each one ran on:
>
> | Trials | Plexus build | Re-run on the final build? |
> |---|---|---|
> | 1/2 (long session, compaction) | `p12` @ `3521a0c` | no |
> | 3/4, 5 (sessions; clone handoff) | `p12` @ `3521a0c` | no |
> | 6, 7, 8 (cross-repo; parallel worktrees + ci-bot; provenance) | `trials-int` @ `76da7d7` | no |
> | 8, Plexus arm with multi-source facts (A11) | `main` @ `7618d18` | yes (this is the final product code) |
>
> The baseline and CLAUDE.md arms don't use Plexus, so the Plexus build doesn't affect them.

Numbers come from [RESULTS.md](RESULTS.md) (generated). Predictions and every change made after
the fact are in [PREREGISTRATION.md](PREREGISTRATION.md). Total spend: ~$21 (API-equivalent,
corrected for the trials 1/2 cost bug, A6; trials 1/2 are $4.59 of it, trials 6-8 $10.42).

## 1. Plain Claude Code is not memoryless

The original premise was "no Plexus = no memory across sessions". That's wrong for current
Claude Code. In 4 of 4 baseline runs, nobody told session 1 to save anything, and it still did:

- 3 runs wrote Claude Code **auto-memory** to
  `~/.claude/projects/<repo-path>/memory/compliance-rules.md`, with the rule, the *why*, and *how to
  apply* it. Claude Code loads this into every later session in the same directory.
- 1 run created and committed a `CLAUDE.md`.

Later sessions then quoted the rules back ("Per the saved compliance rules…") and followed them.

## 2. Same repo, same machine: three-way tie (trials 3/4)

| Arm | Violations (of 24) | Cost/run |
|---|---|---|
| Claude Code, no instruction | 0 | $0.25 |
| Claude Code + "keep decisions in CLAUDE.md" | 0 | $0.23 |
| Claude Code + Plexus | 0 | $0.29 |

When the work stays in one folder on one machine, native memory already carries team decisions
across sessions, and Plexus adds nothing but ~20% cost.

## 3. Handing off to a fresh clone: native auto-memory breaks (trial 5, exploratory)

Here session 1 runs in one checkout and sessions 2-4 run in a `git clone`: a teammate, another
machine, or a new checkout. Only committed files travel.

| Arm | Violations (of 24) | What happened | Cost/run |
|---|---|---|---|
| Claude Code, no instruction | **16** (4 in every run) | auto-memory stayed with the old path; the clone had none. Hard-deleted 12/12 times; dropped normalization on `copy` 4/4 | $0.23 |
| Claude Code + CLAUDE.md | 0 | CLAUDE.md committed in 4/4, so it travelled | $0.22 |
| Claude Code + Plexus | 0 | decisions live in the tenant, independent of path | $0.31 |

The trap only springs when the decision isn't visible in the code. D2 held on `quick-add` and
`rename` even without memory, because the existing `add` command already shows the pattern to copy.
It failed on `copy`, where nothing nearby demonstrates it.

**Takeaway for daily use:** the failure is "decisions kept in local, path-keyed memory", and a
committed `CLAUDE.md` fixes it for free. Plexus fixes it too and ties `CLAUDE.md` here. Its
advantage would have to come from cases a repo file can't cover: decisions that span several repos,
memory shared across different agents and tools, or provenance and contradiction tracking. None of
those were tested in this round.

## 4. One long session (trials 1/2): compaction can erase the rules; Plexus kept them

Setup: Haiku 5.5, 100 prompts in one session, 4 rules set only in prompt 1. Turns 1-~38 ran with no
compaction. The runs were then resumed with `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000` (A5), so each
run compacted 5-7 times. 2 runs per arm, so read every result here as n=2.

| Arm / run | Violations (prompts 2-99) | Probe@90 (of 5) | Prompt 47 | Prompt 100 restates rules | Cost |
|---|---|---|---|---|---|
| baseline r1 | **74** (55 missing takeaway, 14 replica, 5 no Kestrel) | **0** | wrote Python, flagged | no | $1.13 |
| baseline r2 | 5 | 5 | kept Go, flagged | yes | $1.05 |
| plexus r1 | 7 (all "replica") | 5 | kept Go, flagged | yes | $1.27 |
| plexus r2 | 3 (all "replica") | 5 | wrote Python, flagged | yes | $1.14 |

- **One compaction erased the rules completely.** baseline_r1 followed every rule until its
  second compaction (prompt 45). From then on it never ended a message with `Key takeaway:` (55
  of 55 turns), dropped Kestrel from worked examples, and used "replica" again. At the probe it
  said: *"I can't find any of those agreements in this conversation."* At prompt 100 it said the
  rules "aren't in the record I have of this session", because the compaction summary began at a
  later prompt. baseline_r2 went through the same number of compactions and kept everything. So
  Claude Code's compaction summary *sometimes* keeps rules set early in the session and sometimes
  drops them, and from inside the session there's no way to tell which happened.
- **Plexus: no run lost a rule.** Both runs scored 5/5 at the probe and restated all four rules
  at 100. The decile curve stays flat after compaction (Plexus [4,1,1,0,2,0,0,0,1,1] vs baseline
  [2,3,0,0,9,14,13,15,11,12]). Every remaining Plexus slip is "replica", mostly in early
  consensus sections where it's the field's standard term.
- **Engagement differed.** plexus_r1 called `recall` on 47 of 100 turns; plexus_r2 called it on
  only 9 (none in turns 1-38). So r2's clean result can't be credited to recall alone.
  Rules stored in the tenant are the safety net. Whether the agent consults it is up to the model.
- **The prompt-47 contradiction tied.** All 4 runs flagged the reviewer's Python note as conflicting
  with the Go rule. In each arm, one run then kept Go and one switched to Python. Recall didn't
  change the decision: plexus_r1 (heavy recall) kept Go, while plexus_r2 (light recall) switched.
- **Cost:** about $1.1-1.3 per 100-prompt run. Plexus costs ~10% more ($1.20 vs $1.09 mean).
  The earlier "$34.73 / ~$0.50 per turn" was a runner bug: it summed Claude Code's running session
  total (A6). The real cost is ~30x lower, so the runs never needed to stop early.
- **Scorer caveat:** the prompt-100 "calls the Python note a conflict" flag is true for
  baseline_r1, but that's a false positive: the reply says it *can't see* the note. The flag
  doesn't feed into any headline number.

**Takeaway:** in one long session, Claude Code's own compaction is the weak point. 1 of 2
baseline runs silently lost all four rules mid-session, and the 2 Plexus runs didn't. This is
the first trial in this round where Plexus beat plain Claude Code. It rests on one failure among
2 runs per arm, so it needs r3/r4 (≈$1.1 each at real cost) before it's a solid result.

## 5. The cases trials 1-5 left untested (trials 6-8, Sonnet/Haiku 5.5, 4 runs per arm)

Pre-registered as A7/A8 before any scored run. Build `trials-int` (main + p12). Tables:
[RESULTS_T678.md](RESULTS_T678.md). Real cost: $6.77 scored + $3.64 smoke.

| Trial | baseline | CLAUDE.md | Plexus | Cost/run (b / c / p) |
|---|---|---|---|---|
| 6: decision made in repo A, work done in repo B (violations of 24) | 24 | 24 | **0** | $0.26 / $0.28 / $0.36 |
| 7: parallel worktrees, unmerged branch + non-LLM ci-bot (violations of 12) | 9 | 8 | **0** | $0.07 / $0.07 / $0.08 |
| 8: retract a void source (rules correctly kept of 8 / memo-only C3 correctly removed of 4) | 8 / 0* | 8 / 4 | 8 / 4 | $0.16 / $0.18 / $0.25 |

\* In trial 8, every baseline run refused to guess which rules came only from the memo and
changed nothing in session 3. That's an honest no-op, not a wrong retraction.

**Trial 6: across repos, only shared memory reached the second repo.**
- In 4/4 runs the CLAUDE.md arm wrote the decisions into repo A's CLAUDE.md and committed it,
  even noting they apply to `../tasksync`. Sessions in B then looked for a CLAUDE.md only in B,
  found none, and broke both rules in every new exporter.
- No session 1 in any arm touched B.
- Plexus sessions 2-4 called `recall` every time (12/12) and followed both rules on all 24
  opportunities.
- A file-based fix exists (write the note into each repo, or into a shared parent folder, which
  Claude Code also loads), but no agent used one unprompted.

**Trial 7: auto-memory crosses worktrees; CLAUDE.md on a branch only half does.**
- Claude Code keys auto-memory by the main checkout, so all worktrees of a repo share it (12/12
  runs). In the one baseline run where agent A wrote an auto-memory note (r3), agent B followed
  the rule.
- The CLAUDE.md arm's A committed its CLAUDE.md on its unmerged branch in 4/4 runs. B, told to
  check CLAUDE.md, went looking on A's branch or in A's worktree in 3/4 runs. It followed Y1 in 2/4.
- The deprecation notice from the non-LLM ci-bot sat in `CI_NOTES.md`, which no agent read (0/16
  B sessions). Baseline and CLAUDE.md B called the deprecated function in 7/8 runs.
- In Plexus, the bot wrote the notice to the tenant, and Haiku B recalled it every time:
  0 violations in 12 opportunities.

**Trial 8: provenance tied with a well-instructed CLAUDE.md, and showed a gap in Plexus.**
- Both memory arms recorded the source of each rule and retracted exactly the memo-only rules
  (C1 and P1 kept, C3 removed, in 4/4 runs each). In the CLAUDE.md arm, C2 had already been
  dropped in session 2.
- **Plexus's provenance graph was incomplete.** `assert_fact` takes a single `source_id`. Agents
  linked C1 only to the memo and wrote "also product P2" into the fact's text. Session 3 got C1 right
  by reading that text, not by tracing source links, and no agent called `quarantine_source` or
  `why`. A `quarantine_source(memo)` would have hidden C1 wrongly. A fact can't name two
  sources; that's a product fix.
- **Contradiction (session 2):** all CLAUDE.md and Plexus runs flagged the conflict with the
  redaction rule, and baseline flagged it in 3/4 runs. What they did next differed: CLAUDE.md
  complied in 4/4 runs, Plexus kept the rule in 4/4. Plexus's write-time `contradicts` fired 0 times
  in 22 asserts, but it was never really exercised. Session 2 wrote no facts. Session 3's agent
  replaced builder-1's facts with `supersede=true`, an explicit override that is not reported as a
  contradiction by design.

**Trial 8 re-run on the fixed build (P13 multi-source provenance, A11; plexus arm, 4 runs, $0.94).**
`assert_fact` now takes `source_ids`. Tool descriptions tell the agent to pass every supporting document,
and say when to use `quarantine_source` / `forget_source`. A source is only cascaded where no other live
source supports the fact.
- Session 1 linked C1 to both documents in **4/4** runs (originally 0/4).
- Session 3 retracted through the graph in **4/4** runs (2x `forget_source`, 2x `quarantine_source`;
  originally 0/4, when the agents rewrote facts by hand). Each call returned the exact answer: C2 and C3
  hidden or forgotten, C1 kept as "corroborated by the spec". The agents then removed exactly that code.
- Final rule states are still 4/4 correct. Cost is $0.23 per run (was $0.25).

So the provenance gap was a write-surface problem, and fixing it changed agent behaviour: the graph
now does the retraction instead of the agent's reading of free text.

**Takeaway across trials 1-8.** Plexus wins where no file reaches the next agent: another repo
(6), an unmerged branch or a non-LLM tool's note (7), and a single long session through compaction
(1/2, n=2). It ties a committed, well-instructed CLAUDE.md where one does reach (3/4, 5, 8). It
costs 15-40% more per run, at a real ~$0.08-0.36 per run. Its provenance graph is only as good as the agent's writes. In trial 8 it first missed the double-sourced rule; with multi-source facts (P13) the re-run linked it in 4/4 runs and retracted through the graph in 4/4.