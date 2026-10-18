# Crucible L5 results

Run 2026-10-17T21:59:57Z, code 93c1b45, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1094 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 78.6% | 98.6% | 100.0% | 100.0% | 100.0% | 100.0% | 42.7% | 375 | - | 35 | 5 | 0.0% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 38.6% | 360 | 0 | 20 | 0 | 0.0% | 3.26 |
| sep+mult | 84.3% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 44.3% | 387 | 0 | 27 | 0 | 0.0% | 3.02 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 7 | 0 | 29 | 4 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 7 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0032 | 0.0082 | 0.0158 | 0.0364 | 0.0600 |
| sep | 140 | 0.0030 | 0.0074 | 0.0178 | 0.0345 | 0.0520 |
| sep+mult | 140 | 0.0024 | 0.0072 | 0.0228 | 0.0421 | 0.0679 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [1.0, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
