# Crucible L5 results

Run 2026-10-15T20:39:49Z, code 75bd122-dirty, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 742 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss |
|---|---|---|---|---|---|---|---|---|---|
| off | 75.0% | 95.7% | 98.6% | 97.5% | 100.0% | 100.0% | 26.3% | 328 | - |
| on | 42.9% | 77.9% | 87.1% | 96.2% | 100.0% | 70.6% | 11.9% | 266 | 1 |
| on+sweep | 42.1% | 71.4% | 87.1% | 96.2% | 100.0% | 70.6% | 7.3% | 257 | 1 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 8 | 1 | 41 | 4 | 0 |
| on | 0 | 10 | 189 | 0 | 0 |
| on+sweep | 0 | 30 | 186 | 3 | 0 |

Sweep (real, `on+sweep`): 184 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 15, 'noise': 169}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b critical-probe loss = 0 (on, on+sweep) | yes | FAIL | [1, 1] |
| L5b no critical fact moved to dormant | yes | PASS | 0 |
| L5b fact count unchanged by the sweep | yes | PASS | [480, 480] |
| L5b recall@5 of 'on' within 0.02 of 'off' | no | FAIL | [0.9857142857142858, 0.8714285714285714] |
| L5b noise share reduced | no | PASS | [0.26285714285714284, 0.07285714285714286] |
