# Crucible L5 results

Run 2026-10-17T21:17:13Z, code ae17aee, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 1051 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 85.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 40.9% | 388 | - | 21 | 0 | 0.0% | n/a |
| sep-entity | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 42.4% | 392 | 0 | 20 | 0 | 0.0% | 5.22 |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 42.4% | 392 | 0 | 20 | 0 | 0.0% | 3.83 |
| sep+mult | 85.7% | 97.9% | 100.0% | 100.0% | 100.0% | 100.0% | 41.6% | 388 | 0 | 30 | 0 | 0.0% | 3.86 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 1 | 0 | 20 | 0 | 0 |
| sep-entity | 0 | 0 | 20 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 10 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0060 | 0.0131 | 0.0360 | 0.0667 | 0.0876 |
| sep-entity | 140 | 0.0069 | 0.0139 | 0.0361 | 0.0674 | 0.0876 |
| sep | 140 | 0.0069 | 0.0139 | 0.0361 | 0.0674 | 0.0876 |
| sep+mult | 140 | 0.0072 | 0.0198 | 0.0385 | 0.0708 | 0.0903 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| PC sep recall@1 >= 0.95 | no | FAIL | [0.8571428571428571] |
| PC sep recall@1 > sep-entity + 0.02 (falsified otherwise: no gain beyond id noise) | yes | FAIL | [0.8571428571428571, 0.8571428571428571] |
| PC sep same-entity rows above target <= 5 | no | FAIL | [20] |
| PC sep recall@5 >= sep-entity recall@5 | no | PASS | [1.0, 1.0] |
| PC sep noise share <= sep-entity + 0.01 | no | PASS | [0.42428571428571427, 0.42428571428571427] |
| PC sep+mult recall@1 within 1 probe (0.0072) of sep | no | PASS | [0.8571428571428571, 0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [1.0, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
