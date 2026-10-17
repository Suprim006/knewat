# Crucible L5 results

Run 2026-10-17T21:01:38Z, code ae17aee, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 739 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 79.3% | 98.6% | 99.3% | 98.8% | 100.0% | 100.0% | 28.3% | 342 | - | 31 | 8 | 2.0% | n/a |
| sep-entity | 84.3% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 33.4% | 359 | 0 | 22 | 0 | 0.0% | 2.71 |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 31.7% | 351 | 0 | 20 | 0 | 0.0% | 2.53 |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 32.3% | 352 | 0 | 21 | 0 | 0.0% | 3.03 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 1 | 2 | 32 | 4 | 0 |
| sep-entity | 0 | 0 | 22 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 1 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0045 | 0.0085 | 0.0192 | 0.0402 | 0.0692 |
| sep-entity | 140 | 0.0058 | 0.0102 | 0.0203 | 0.0414 | 0.0707 |
| sep | 140 | 0.0045 | 0.0094 | 0.0198 | 0.0410 | 0.0692 |
| sep+mult | 140 | 0.0045 | 0.0102 | 0.0203 | 0.0402 | 0.0668 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| PC sep recall@1 >= 0.95 | no | FAIL | [0.8571428571428571] |
| PC sep recall@1 > sep-entity + 0.02 (falsified otherwise: no gain beyond id noise) | yes | FAIL | [0.8428571428571429, 0.8571428571428571] |
| PC sep same-entity rows above target <= 5 | no | FAIL | [20] |
| PC sep recall@5 >= sep-entity recall@5 | no | PASS | [1.0, 1.0] |
| PC sep noise share <= sep-entity + 0.01 | no | PASS | [0.3342857142857143, 0.3171428571428571] |
| PC sep+mult recall@1 within 1 probe (0.0072) of sep | no | PASS | [0.8571428571428571, 0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9928571428571429, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
