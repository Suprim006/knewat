# Crucible L5 results

Run 2026-10-17T21:55:28Z, code 9f50190, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1083 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 80.7% | 97.9% | 100.0% | 100.0% | 100.0% | 100.0% | 44.6% | 379 | - | 29 | 7 | 0.0% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 39.7% | 365 | 0 | 20 | 0 | 0.0% | 3.06 |
| sep+mult | 85.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 40.7% | 375 | 0 | 26 | 0 | 0.0% | 3.26 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 5 | 0 | 29 | 2 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 6 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0031 | 0.0085 | 0.0189 | 0.0378 | 0.0580 |
| sep | 140 | 0.0031 | 0.0083 | 0.0184 | 0.0352 | 0.0488 |
| sep+mult | 140 | 0.0035 | 0.0101 | 0.0211 | 0.0390 | 0.0649 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [1.0, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
