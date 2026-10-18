# Crucible L5 results

Run 2026-10-15T20:38:08Z, code 75bd122-dirty, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 739 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss |
|---|---|---|---|---|---|---|---|---|---|
| off | 75.7% | 97.1% | 98.6% | 97.5% | 100.0% | 100.0% | 22.7% | 321 | - |
| on | 62.9% | 92.1% | 96.4% | 97.5% | 100.0% | 94.1% | 14.1% | 279 | 0 |
| on+sweep | 62.9% | 85.7% | 87.1% | 97.5% | 100.0% | 68.6% | 9.6% | 269 | 0 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 4 | 0 | 42 | 5 | 0 |
| on | 0 | 5 | 91 | 1 | 0 |
| on+sweep | 0 | 25 | 99 | 10 | 0 |

Sweep (real, `on+sweep`): 184 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 16, 'noise': 168}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b critical-probe loss = 0 (on, on+sweep) | yes | PASS | [0, 0] |
| L5b no critical fact moved to dormant | yes | PASS | 0 |
| L5b fact count unchanged by the sweep | yes | PASS | [480, 480] |
| L5b recall@5 of 'on' within 0.02 of 'off' | no | FAIL | [0.9857142857142858, 0.9642857142857143] |
| L5b noise share reduced | no | PASS | [0.22714285714285715, 0.09571428571428571] |
