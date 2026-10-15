# Crucible L5 results

Run 2026-10-15T20:34:17Z, code 75bd122-dirty, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1097 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss |
|---|---|---|---|---|---|---|---|---|---|
| off | 76.4% | 97.1% | 97.9% | 96.2% | 100.0% | 100.0% | 31.0% | 339 | - |
| on | 22.9% | 53.6% | 79.3% | 87.5% | 100.0% | 62.7% | 14.0% | 273 | 7 |
| on+sweep | 17.1% | 42.9% | 67.9% | 82.5% | 100.0% | 39.2% | 9.6% | 260 | 11 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 3 | 1 | 41 | 4 | 0 |
| on | 1 | 10 | 330 | 0 | 0 |
| on+sweep | 2 | 25 | 375 | 0 | 0 |

Sweep (real, `on+sweep`): 587 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 15, 'noise': 572}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b critical-probe loss = 0 (on, on+sweep) | yes | FAIL | [7, 11] |
| L5b no critical fact moved to dormant | yes | PASS | 0 |
| L5b fact count unchanged by the sweep | yes | PASS | [1080, 1080] |
| L5b recall@5 of 'on' within 0.02 of 'off' | no | FAIL | [0.9785714285714285, 0.7928571428571428] |
| L5b noise share reduced | no | PASS | [0.31, 0.09571428571428571] |
