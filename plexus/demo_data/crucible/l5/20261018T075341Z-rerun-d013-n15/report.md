# Crucible L5 results

Run 2026-10-18T07:53:41Z, code 7f28f60, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1096 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 80.0% | 97.9% | 99.3% | 98.8% | 100.0% | 100.0% | 41.9% | 373 | - | 32 | 6 | 0.0% | n/a |
| kw-fix | 62.9% | 93.6% | 100.0% | 100.0% | 100.0% | 100.0% | 36.3% | 352 | 0 | 79 | 15 | 5.9% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 38.3% | 359 | 0 | 20 | 0 | 0.0% | 5.25 |
| sep+mult | 81.4% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 41.4% | 376 | 0 | 30 | 0 | 0.0% | 3.52 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 4 | 0 | 30 | 4 | 0 |
| kw-fix | 44 | 4 | 46 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 6 | 0 | 24 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0043 | 0.0083 | 0.0187 | 0.0351 | 0.0551 |
| kw-fix | 140 | -0.0371 | 0.0030 | 0.0258 | 0.0477 | 0.0592 |
| sep | 140 | 0.0031 | 0.0083 | 0.0184 | 0.0325 | 0.0449 |
| sep+mult | 140 | 0.0007 | 0.0072 | 0.0206 | 0.0396 | 0.0592 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| PC sep recall@1 >= 0.95 | no | FAIL | [0.8571428571428571] |
| PC sep same-entity rows above target <= 5 | no | FAIL | [20] |
| PC sep+mult recall@1 within 1 probe (0.0072) of sep | no | FAIL | [0.8571428571428571, 0.8142857142857143] |
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9928571428571429, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
| L5b-D013 kw-fix recall@1 (report only) | no | PASS | 0.6285714285714286 |
