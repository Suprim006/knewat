# Crucible L5 results

Run 2026-10-17T21:03:48Z, code ae17aee, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1094 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 78.6% | 98.6% | 99.3% | 98.8% | 100.0% | 100.0% | 41.6% | 373 | - | 33 | 7 | 0.0% | n/a |
| sep-entity | 84.3% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 39.6% | 366 | 0 | 22 | 0 | 0.0% | 2.58 |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 36.9% | 357 | 0 | 20 | 0 | 0.0% | 2.51 |
| sep+mult | 85.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 41.6% | 377 | 0 | 23 | 0 | 0.0% | 2.62 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 3 | 0 | 32 | 5 | 0 |
| sep-entity | 0 | 0 | 22 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 3 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0042 | 0.0082 | 0.0184 | 0.0332 | 0.0582 |
| sep-entity | 140 | 0.0045 | 0.0087 | 0.0187 | 0.0332 | 0.0477 |
| sep | 140 | 0.0030 | 0.0074 | 0.0178 | 0.0327 | 0.0449 |
| sep+mult | 140 | 0.0035 | 0.0085 | 0.0195 | 0.0371 | 0.0586 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| PC sep recall@1 >= 0.95 | no | FAIL | [0.8571428571428571] |
| PC sep recall@1 > sep-entity + 0.02 (falsified otherwise: no gain beyond id noise) | yes | FAIL | [0.8428571428571429, 0.8571428571428571] |
| PC sep same-entity rows above target <= 5 | no | FAIL | [20] |
| PC sep recall@5 >= sep-entity recall@5 | no | PASS | [1.0, 1.0] |
| PC sep noise share <= sep-entity + 0.01 | no | PASS | [0.39571428571428574, 0.36857142857142855] |
| PC sep+mult recall@1 within 1 probe (0.0072) of sep | no | PASS | [0.8571428571428571, 0.85] |
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9928571428571429, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
