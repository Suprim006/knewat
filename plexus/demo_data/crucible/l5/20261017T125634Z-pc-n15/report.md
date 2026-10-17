# Crucible L5 results

Run 2026-10-17T12:56:34Z, code 468601e, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1091 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 76.4% | 96.4% | 98.6% | 97.5% | 100.0% | 100.0% | 31.0% | 337 | - | 40 | 11 | 0.0% | n/a |
| sep-entity | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 32.9% | 343 | 0 | 20 | 0 | 0.0% | 2.46 |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 43.6% | 380 | 0 | 20 | 0 | 0.0% | 2.73 |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 31.6% | 350 | 0 | 20 | 0 | 0.0% | 2.77 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 6 | 2 | 40 | 3 | 0 |
| sep-entity | 0 | 0 | 20 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 0 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0019 | 0.0044 | 0.0162 | 0.0443 | 0.0704 |
| sep-entity | 140 | 0.0024 | 0.0071 | 0.0183 | 0.0401 | 0.0625 |
| sep | 140 | 0.0029 | 0.0093 | 0.0309 | 0.0543 | 0.0749 |
| sep+mult | 140 | 0.0025 | 0.0093 | 0.0333 | 0.0606 | 0.0895 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| PC sep recall@1 >= 0.95 | no | FAIL | [0.8571428571428571] |
| PC sep recall@1 > sep-entity + 0.02 (falsified otherwise: no gain beyond id noise) | yes | FAIL | [0.8571428571428571, 0.8571428571428571] |
| PC sep same-entity rows above target <= 5 | no | FAIL | [20] |
| PC sep recall@5 >= sep-entity recall@5 | no | PASS | [1.0, 1.0] |
| PC sep noise share <= sep-entity + 0.01 | no | FAIL | [0.32857142857142857, 0.4357142857142857] |
| PC sep+mult recall@1 within 1 probe (0.0072) of sep | no | PASS | [0.8571428571428571, 0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9857142857142858, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
