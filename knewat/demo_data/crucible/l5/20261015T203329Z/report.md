# Crucible L5 results

Run 2026-10-15T20:33:29Z, code 75bd122-dirty, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 732 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss |
|---|---|---|---|---|---|---|---|---|---|
| off | 75.0% | 97.1% | 98.6% | 97.5% | 100.0% | 100.0% | 27.1% | 330 | - |
| on | 19.3% | 45.0% | 75.0% | 87.5% | 100.0% | 51.0% | 9.9% | 258 | 8 |
| on+sweep | 15.0% | 41.4% | 65.7% | 82.5% | 100.0% | 33.3% | 6.0% | 250 | 12 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 4 | 1 | 42 | 4 | 0 |
| on | 1 | 12 | 367 | 0 | 0 |
| on+sweep | 1 | 29 | 379 | 3 | 0 |

Sweep (real, `on+sweep`): 187 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 15, 'noise': 172}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b critical-probe loss = 0 (on, on+sweep) | yes | FAIL | [8, 12] |
| L5b no critical fact moved to dormant | yes | PASS | 0 |
| L5b fact count unchanged by the sweep | yes | PASS | [480, 480] |
| L5b recall@5 of 'on' within 0.02 of 'off' | no | FAIL | [0.9857142857142858, 0.75] |
| L5b noise share reduced | no | PASS | [0.2714285714285714, 0.06] |
