# Crucible L5 results

Run 2026-10-15T20:40:36Z, code 75bd122-dirty, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 739 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss |
|---|---|---|---|---|---|---|---|---|---|
| off | 75.7% | 97.1% | 98.6% | 97.5% | 100.0% | 100.0% | 23.3% | 323 | - |
| on | 69.3% | 97.9% | 98.6% | 97.5% | 100.0% | 100.0% | 18.4% | 297 | 0 |
| on+sweep | 67.1% | 86.4% | 87.9% | 97.5% | 100.0% | 70.6% | 14.4% | 283 | 0 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 4 | 0 | 42 | 5 | 0 |
| on | 0 | 0 | 56 | 0 | 0 |
| on+sweep | 0 | 10 | 96 | 14 | 0 |

Sweep (real, `on+sweep`): 186 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 15, 'noise': 171}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b critical-probe loss = 0 (on, on+sweep) | yes | PASS | [0, 0] |
| L5b no critical fact moved to dormant | yes | PASS | 0 |
| L5b fact count unchanged by the sweep | yes | PASS | [480, 480] |
| L5b recall@5 of 'on' within 0.02 of 'off' | no | PASS | [0.9857142857142858, 0.9857142857142858] |
| L5b noise share reduced | no | PASS | [0.23285714285714285, 0.1442857142857143] |
