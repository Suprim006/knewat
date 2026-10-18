# Crucible L5 results

Run 2026-10-17T21:51:35Z, code 9f50190, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1090 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 80.7% | 98.6% | 99.3% | 98.8% | 100.0% | 100.0% | 40.4% | 371 | - | 32 | 5 | 0.0% | n/a |
| sep | 82.9% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 24.3% | 332 | 0 | 20 | 4 | 0.0% | 0.00 |
| sep+mult | 68.6% | 98.6% | 100.0% | 100.0% | 100.0% | 100.0% | 17.7% | 309 | 0 | 27 | 27 | 35.3% | 0.01 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 2 | 0 | 30 | 5 | 0 |
| sep | 0 | 0 | 24 | 0 | 0 |
| sep+mult | 0 | 18 | 35 | 1 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0035 | 0.0077 | 0.0184 | 0.0362 | 0.0570 |
| sep | 140 | 0.0058 | 0.0087 | 0.0255 | 0.0362 | 0.0492 |
| sep+mult | 140 | -0.0231 | 0.0059 | 0.0157 | 0.0348 | 0.0633 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8285714285714286] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | FAIL | [0.8285714285714286] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9928571428571429, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
