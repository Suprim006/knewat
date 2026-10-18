# Crucible L5 results

Run 2026-10-17T12:57:38Z, code 468601e, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 1051 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 75.0% | 96.4% | 98.6% | 97.5% | 100.0% | 100.0% | 24.9% | 325 | - | 40 | 12 | 0.0% | n/a |
| sep-entity | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 29.6% | 341 | 0 | 20 | 0 | 0.0% | 2.52 |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 33.1% | 363 | 0 | 20 | 0 | 0.0% | 2.83 |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 26.9% | 346 | 0 | 20 | 0 | 0.0% | 2.50 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 6 | 1 | 41 | 4 | 0 |
| sep-entity | 0 | 0 | 20 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 0 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0019 | 0.0044 | 0.0167 | 0.0486 | 0.0707 |
| sep-entity | 140 | 0.0024 | 0.0078 | 0.0277 | 0.0504 | 0.0732 |
| sep | 140 | 0.0029 | 0.0093 | 0.0332 | 0.0553 | 0.0768 |
| sep+mult | 140 | 0.0025 | 0.0093 | 0.0333 | 0.0707 | 0.0895 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| PC sep recall@1 >= 0.95 | no | FAIL | [0.8571428571428571] |
| PC sep recall@1 > sep-entity + 0.02 (falsified otherwise: no gain beyond id noise) | yes | FAIL | [0.8571428571428571, 0.8571428571428571] |
| PC sep same-entity rows above target <= 5 | no | FAIL | [20] |
| PC sep recall@5 >= sep-entity recall@5 | no | PASS | [1.0, 1.0] |
| PC sep noise share <= sep-entity + 0.01 | no | FAIL | [0.2957142857142857, 0.3314285714285714] |
| PC sep+mult recall@1 within 1 probe (0.0072) of sep | no | PASS | [0.8571428571428571, 0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9857142857142858, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
