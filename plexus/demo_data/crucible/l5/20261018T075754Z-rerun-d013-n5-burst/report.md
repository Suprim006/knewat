# Crucible L5 results

Run 2026-10-18T07:57:54Z, code 7f28f60, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 1051 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 79.3% | 97.9% | 99.3% | 98.8% | 100.0% | 100.0% | 32.4% | 351 | - | 34 | 6 | 0.0% | n/a |
| kw-fix | 82.1% | 97.1% | 100.0% | 100.0% | 100.0% | 100.0% | 32.4% | 344 | 0 | 40 | 4 | 0.0% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 33.4% | 358 | 0 | 20 | 0 | 0.0% | 2.74 |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 33.4% | 355 | 0 | 24 | 0 | 0.0% | 2.67 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 3 | 1 | 32 | 4 | 0 |
| kw-fix | 20 | 0 | 24 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 4 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0045 | 0.0087 | 0.0192 | 0.0378 | 0.0633 |
| kw-fix | 140 | 0.0072 | 0.0159 | 0.0308 | 0.0444 | 0.0591 |
| sep | 140 | 0.0045 | 0.0102 | 0.0201 | 0.0401 | 0.0633 |
| sep+mult | 140 | 0.0045 | 0.0122 | 0.0231 | 0.0397 | 0.0591 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| PC sep recall@1 >= 0.95 | no | FAIL | [0.8571428571428571] |
| PC sep same-entity rows above target <= 5 | no | FAIL | [20] |
| PC sep+mult recall@1 within 1 probe (0.0072) of sep | no | PASS | [0.8571428571428571, 0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9928571428571429, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
| L5b-D013 kw-fix recall@1 (report only) | no | PASS | 0.8214285714285714 |
