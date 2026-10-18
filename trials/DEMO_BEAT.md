# Demo video proposal: lead with trials 6, 7 and 8

Proposal only. `docs/VIDEO_SCRIPT.md` is not edited. Numbers are from `trials/FINDINGS.md`, `trials/RESULTS_T678.md`
and `trials/PREREGISTRATION.md`. The timings and word counts below were checked with the same regex and rules as
`scripts/verify_readme.py` (9 beats, contiguous times, ends by 3:00, narration <= 25 words).

## (a) One replacement beat

**Replaces beat 5 (Time Machine, 1:05-1:22).** Beats 4, 5 and 6 all tell the v1 to v2 story: beat 4 shows v1 superseded
by v2, beat 5 reads v1 then v2 at two steps, beat 6 traces the decision to the v2 fact and the `SUPERSEDES` link back to
v1. Beat 5 is the one that adds least on screen. `knew_at` is still named in beat 9's ablation table, and the Time Machine
stays in the README and the live View.

What it costs: the Time Machine no longer appears in the video, and beat 9 lists `knew_at` as BROKEN without having
shown it. If you would rather keep it, the next-weakest candidate is beat 2 (Flow replay), but that one sets up beat 3.

Copy-paste row, in the exact format `verify_readme.py` parses (narration is 25 words):

```
| 5 | 1:05-1:30 | Browser: `trials/FINDINGS.md` section 5 table, or a slide of it. Highlight trial 6 (violations of 24: baseline 24, CLAUDE.md 24, Plexus 0) and trial 7 (of 12: 9, 8, 0). Caption: "4 runs per arm. Scored by running the code. Small synthetic repos." Cut to the trial 8 `quarantine_source` result from `trials/logs/t8/plexus_p13r3/session_3.jsonl`: highlight `fact_ids` (2), `readers_total` 4, `corroborated_total` 1. Caption: "Memo declared void: 2 facts hidden, C1 kept (corroborated by the spec)". Last 3 s, one line: "Ties a committed CLAUDE.md where a file reaches the next agent (trial 8: 4 of 4 in both arms)." | "Rule set in another repo: Claude Code broke it 24 of 24 times, Plexus never. Void a memo; the graph keeps what another source backs." |
```

Rough shot split for the 25 s: 0-10 s the two result rows, 10-22 s the quarantine output, 22-25 s the tie line. The
tie line is not decoration. The script's own honesty rule (beat 8 note) applies here too: the video should say where
Plexus does not win.

Two orderings, same total (2:58, under the 3:00 limit; the script header says "target 2:50", so update that line):

| Beat | A: in place (swap beat 5) | B: moved to slot 2 (recommended) |
|---|---|---|
| 1 | 0:00-0:12 | 0:00-0:12 |
| new | 1:05-1:30 (slot 5) | 0:12-0:37 (slot 2) |
| old 2 Flow | 0:12-0:30 | 0:37-0:55 (slot 3) |
| old 3 builder killed | 0:30-0:48 | 0:55-1:13 (slot 4) |
| old 4 Explorer | 0:48-1:05 | 1:13-1:30 (slot 5) |
| old 6 Why | 1:30-1:48 | 1:30-1:48 |
| old 7 staleness | 1:48-2:13 | 1:48-2:13 |
| old 8 Results | 2:13-2:36 | 2:13-2:36 |
| old 9 ablation | 2:36-2:58 | 2:36-2:58 |

I recommend B because you want the trials among the first things in the video. Result first, then "here is how the graph
did it" (Flow, builder killed, Explorer) reads naturally. If you pick B, end beat 1 on the README top instead of the
View header, so the cut to the trial rows is clean. For a 2:53 total instead, cut the beat to 20 s by trimming the quarantine shot.

If adopted, also touch these lines in `VIDEO_SCRIPT.md` (not done here): the header ("target 2:50", "Nine beats from
`docs/PLAN.md` P6"), the Time Machine item in "Pre-open", the "Step numbers" note (17 to 38 is no longer used on screen),
and the closing cut-order advice. Two traps for `verify_readme.py`: do not paste UUIDs from the quarantine output into
the script (they come from the trial logs, not from the `acme-claude-sonnet` recording, so the id check would fail), and
any backticked repo path you add (for example `trials/FINDINGS.md`) must exist in the `falkordb` repo, so merge the
trials folder first.

## (b) Opening hooks that lead with the trials

Each is a full replacement for beat 1's narration (<= 25 words) and keeps the one-line pitch. Pick one.

1. "Rules set in one repo, work done in another: Claude Code broke them 24 of 24 times. Plexus keeps shared memory in one FalkorDB graph." (25 words. Trial 6: baseline 24 of 24, and so did the CLAUDE.md arm.)
2. "Parallel agents, an unmerged branch, a bot's notice nobody read: Claude Code broke the rules 9 times in 12. Plexus: zero. It runs on FalkorDB." (25 words. Trial 7: baseline 9 of 12, CLAUDE.md 8 of 12; the notice was read in 0 of 16 sessions.)
3. "A CLAUDE.md works until the next agent isn't in that repo: 24 of 24 rules broken. Plexus keeps memory in one FalkorDB graph." (23 words. Same trial 6 number, framed so the video does not oversell: it concedes the file works when it reaches the agent.)

I would pick 3 or 1. Hook 2 packs three ideas into one line and is the hardest to say aloud. All three need the caption
"4 runs per arm, small synthetic repos" on screen while they are spoken.

## (c) What to show on screen

- **Trial 6 table** (`RESULTS_T678.md`, first table): show the "per run" column (`6, 6, 6, 6` against `0, 0, 0, 0`). It shows
  every run, not an average, and fits on one screen. Crop away the memory-evidence bullets below it; they are unreadable
  at video size.
- **Trial 7 per-command grid** (`RESULTS_T678.md`, "Per-command verdicts"): twelve rows of V and C letters. Baseline and
  CLAUDE.md rows are mostly V, the four Plexus rows are all C. It reads at a glance, and the lone all-C baseline row
  (r3, where auto-memory carried the rule) is honest and visible. Use this in place of the trial 7 sentence if the beat
  needs a second visual.
- **Trial 8 quarantine output**, from the logged real run `plexus_p13r3` (Plexus main at `7618d18`, the final code). The
  real result lists two `fact_ids`, `readers_total` 4 (read by `builder-2` and `builder-3`), `decisions_total` 0 and
  `corroborated_total` 1 with the spec as `other_sources`. Highlight `corroborated` and say "recorded", since it is a
  logged run and not the acme replay. Do not claim more than the output shows: the agents then removed exactly the
  code for the two hidden rules, and C1 and P1 stayed.
- **Do not show** the trial 8 contradiction (session 2) table in this beat. It needs a paragraph of explanation (all
  arms flagged the conflict; CLAUDE.md complied 4 of 4, Plexus kept the rule 4 of 4), and `contradicts` fired 0 of 22
  times in the first run.
- **Builds on screen:** trials 6 and 7 ran on `trials-int` @ `76da7d7`; only the trial 8 quarantine run is on the final
  code. A small footer, "trials 6-7: earlier build; trial 8 re-run: final build", keeps the video consistent with
  `FINDINGS.md`.
