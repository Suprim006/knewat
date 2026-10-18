# Crucible L5 results

Run 2026-10-17T22:09:07Z, code 3521a0c, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1093 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss |
|---|---|---|---|---|---|---|---|---|---|
| off | 84.3% | 99.3% | 100.0% | 100.0% | 100.0% | 100.0% | 57.4% | 421 | - |
| on | 73.6% | 85.7% | 97.9% | 96.2% | 100.0% | 100.0% | 56.0% | 420 | 3 |
| on+sweep | 85.0% | 99.3% | 100.0% | 100.0% | 100.0% | 100.0% | 34.4% | 368 | 0 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 6 | 0 | 20 | 0 | 0 |
| on | 75 | 0 | 20 | 0 | 0 |
| on+sweep | 6 | 0 | 20 | 0 | 0 |

Sweep (real, `on+sweep`): 582 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 582}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b critical-probe loss = 0 (on, on+sweep) | yes | FAIL | [3, 0] |
| L5b no critical fact moved to dormant | yes | PASS | 0 |
| L5b fact count unchanged by the sweep | yes | PASS | [1080, 1080] |
| L5b recall@5 of 'on' within 0.02 of 'off' | no | FAIL | [1.0, 0.9785714285714285] |
| L5b noise share reduced | no | PASS | [0.5742857142857143, 0.3442857142857143] |
