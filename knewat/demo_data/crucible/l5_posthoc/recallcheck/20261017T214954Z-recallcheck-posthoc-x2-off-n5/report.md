# Crucible L5 results

Run 2026-10-17T21:49:54Z, code 9f50190, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 739 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 78.6% | 98.6% | 99.3% | 98.8% | 100.0% | 100.0% | 30.4% | 347 | - | 34 | 5 | 0.0% | n/a |
| sep | 84.3% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 20.3% | 326 | 0 | 20 | 2 | 0.0% | 0.01 |
| sep+mult | 72.9% | 95.7% | 100.0% | 100.0% | 100.0% | 100.0% | 16.7% | 310 | 0 | 26 | 29 | 27.5% | 0.01 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 3 | 0 | 31 | 5 | 0 |
| sep | 0 | 0 | 22 | 0 | 0 |
| sep+mult | 0 | 23 | 32 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0045 | 0.0087 | 0.0192 | 0.0412 | 0.0700 |
| sep | 140 | 0.0045 | 0.0087 | 0.0244 | 0.0374 | 0.0527 |
| sep+mult | 140 | -0.0016 | 0.0069 | 0.0184 | 0.0390 | 0.0662 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8428571428571429] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | FAIL | [0.8428571428571429] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9928571428571429, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
