# Crucible L5 results

Run 2026-10-17T21:42:42Z, code 9f50190, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1087 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 77.9% | 97.9% | 99.3% | 98.8% | 100.0% | 100.0% | 41.0% | 372 | - | 35 | 8 | 0.0% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 37.4% | 357 | 0 | 20 | 0 | 0.0% | 2.59 |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 41.1% | 373 | 0 | 24 | 0 | 0.0% | 2.80 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 6 | 0 | 32 | 5 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 4 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0031 | 0.0085 | 0.0184 | 0.0366 | 0.0653 |
| sep | 140 | 0.0031 | 0.0077 | 0.0180 | 0.0325 | 0.0473 |
| sep+mult | 140 | 0.0043 | 0.0102 | 0.0211 | 0.0367 | 0.0575 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9928571428571429, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
