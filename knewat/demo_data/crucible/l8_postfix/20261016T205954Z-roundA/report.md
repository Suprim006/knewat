# Crucible L8 round A: long-horizon memory under live change (P, B1, B0′ × seeds)

Run `20261016T205954Z-roundA`, code `bbfdea7` (dirty: True), model alias `sonnet`, prompts `l8-v1`. L8 spend (runs + B0′ readers + probe + discarded shake-down): $21.35 (notional `total_cost_usd`, owner's subscription).

## Headline

- Plexus did not reduce stale actions versus SQLite (4.1% vs 5.7%, n = 5 seeds each; not separated by the pre-stated rule) and used 2.61× the tokens per correct action (2.23× billing-weighted); its remaining advantages are the ones L2/L6 established (deterministic, $0 provenance answers).
- Versus unmodified Claude Code with its own memory files (B0′): stale actions 4.1% (P) vs 2.4% (B0′), not separated by the pre-stated rule (a tie).
- Step repetition, missing completion and reasoning–action mismatch were not changed by the memory backend (step repetition P 0.0%, B1 0.0%, B0′ 0.0%; no separation by the pre-stated rule).
- Cost: P used 2.61× B1's tokens per correct action (> 2×): published as a loss on cost (§6.6 criterion).

## Metrics (MAST rows measure three narrow signatures, not the taxonomy categories)

| Metric | P (Plexus) | B1 (SQLite) | B0′ (Claude Code files) |
|---|---|---|---|
| runs (seeds) | 5 | 5 | 5 |
| tasks done / 16 (per seed) | 16, 16, 16, 16, 16 | 16, 16, 16, 16, 16 | 16, 16, 16, 16, 16 |
| turns (per seed) | 22, 22, 22, 22, 22 | 22, 22, 22, 22, 23 | 22, 22, 22, 22, 22 |
| **stale-act rate, pooled** [Wilson 95%] | **4.1%** (13/319) [0.024, 0.0685] | **5.7%** (19/332) [0.0369, 0.0876] | **2.4%** (6/248) [0.0111, 0.0518] |
| stale-act rate per seed | 4.8%, 4.5%, 1.5%, 1.6%, 7.9% | 10.4%, 1.5%, 4.6%, 4.6%, 7.2% | 8.3%, 0.0%, 0.0%, 0.0%, 3.9% |
| stale-act, dependent-only (pooled) | 4.1% | 5.4% | 2.0% |
| stale-act, artifact files only (pooled) | 4.6% | 7.8% | 3.8% |
| stale facts live in store at end (per seed) | 6, 6, 4, 5, 2 | 6, 6, 4, 5, 2 | 6, 6, 4, 6, 1 |
| time-to-notice L1 median turns (per seed) | 3, 3.0, 3.0, 3.0, 5.5 | 3, 3.0, 3.0, 3.0, 7.5 | 2, 3.0, 1.5, 1.5, 5.5 |
| time-to-notice L2 median turns (per seed) | 6.0, 6, 3, 6, 7 | 5.5, 6, 3, 6, 9 | 3.5, 6, 3, 6, 7 |
| notice censored L1 / L2 (of cases) | 4 / 10 (of 41) | 4 / 10 (of 41) | 2 / 9 (of 41) |
| **step repetition (R1+R2+R3), pooled** | **0.0%** (0) | **0.0%** (0) | **0.0%** (0) |
| step repetition per seed | 0.0%, 0.0%, 0.0%, 0.0%, 0.0% | 0.0%, 0.0%, 0.0%, 0.0%, 0.0% | 0.0%, 0.0%, 0.0%, 0.0%, 0.0% |
| missing completion C1+C2+C3 (per seed, of 16) | 1, 1, 0, 0, 1 | 1, 0, 1, 1, 1 | 0, 0, 0, 0, 1 |
| mismatch M1 / M2 / M3 (sum) | 0 / 2 / 5 | 0 / 3 / 5 | 0 / n/a / n/a |
| tokens per correct action, pooled (raw) | 89,521 | 34,248 | 22,190 |
| tokens per correct action, pooled (billing-weighted) | 14,348 | 6,421 | 7,345 |
| cost USD (all seeds) | $9.62 | $5.61 | $6.12 |

Post-hoc robustness variants of the stale-act rate (amendments 2-3; descriptive, not the headline):

| Variant | P (Plexus) | B1 (SQLite) | B0′ (Claude Code files) |
|---|---|---|---|
| excluding the X2 brief-mandated store write | 2.5% (8/314) | 4.0% (13/326) | 2.4% (6/248) |
| excluding actions whose only stale tokens are of deleted functions | 3.5% (11/317) | 4.9% (16/329) | 0.0% (0/242) |
| excluding both | 1.9% (6/312) | 3.1% (10/323) | 0.0% (0/242) |
| only tasks every arm of the seed reached | 4.1% (13/319) | 5.7% (19/332) | 2.4% (6/248) |

## Separation tests (exact permutation on seed-level rates; separated = p ≤ 0.05 and ranges do not overlap)

- P_vs_B1_stale_act: p = 0.5238, ranges overlap = True, **separated = False**
- P_vs_B1_step_repetition: p = 1.0, ranges overlap = True, **separated = False**
- P_vs_B0p_stale_act: p = 0.4365, ranges overlap = True, **separated = False**
- P_vs_B0p_step_repetition: p = 1.0, ranges overlap = True, **separated = False**

## End-of-run audit (§6.5; P Cypher and B1 SQL deterministic, B0′ a 32k BM25 reader)


§7 footnote: median `claim_next_task` latency seen by the agent (stream-json timestamps, incl. the MCP stdio hop): B1 (SQLite) 15 ms (n=96), P (Plexus) 35 ms (n=95). L1 regression gate passed at 42a5750 (amendment 1). Forgetting: product default (on, floor 0.9) in P; no L8 metric depends on it.

## Honesty

- Round A only (P, B1, B0′); B0 and B3 (Postgres with the same tool design) were not run, so the design-vs-graph question of §5.5 is open.
- n = 5 seeds per arm (if fewer, the table says so); claude -p has no seed, the seeds fix the fault schedule only.
- Synthetic sentinels, synthetic repo, one scenario family, one model (Sonnet via the owner's subscription; costs are notional), one machine.
- MAST rows are three deterministic signatures per mode, not Cemri et al.'s annotated categories.
- Implementation choices the plan left open are listed in amendment 1 of docs/research/L8_LONG_HORIZON_OUTCOMES.md.
