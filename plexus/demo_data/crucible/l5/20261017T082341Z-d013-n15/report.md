# Crucible L5 results

Run 2026-10-17T08:23:41Z, code 3017ad7, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1094 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 77.1% | 97.1% | 98.6% | 97.5% | 100.0% | 100.0% | 28.7% | 332 | - | 35 | 12 | 2.0% | n/a |
| on-mult | 65.7% | 91.4% | 96.4% | 97.5% | 100.0% | 94.1% | 17.4% | 285 | 0 | 47 | 46 | 3.9% | n/a |
| kw-fix | 77.1% | 97.1% | 98.6% | 97.5% | 100.0% | 100.0% | 17.4% | 286 | 0 | 31 | 17 | 0.0% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 23.7% | 319 | 0 | 20 | 0 | 0.0% | 2.48 |
| sep+add | 70.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 20.1% | 307 | 0 | 40 | 6 | 0.0% | 2.51 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 1 | 2 | 41 | 3 | 0 |
| on-mult | 0 | 6 | 87 | 0 | 0 |
| kw-fix | 0 | 4 | 44 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+add | 0 | 0 | 46 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0020 | 0.0050 | 0.0167 | 0.0431 | 0.0643 |
| on-mult | 140 | -0.0020 | 0.0040 | 0.0239 | 0.0411 | 0.0625 |
| kw-fix | 140 | 0.0018 | 0.0060 | 0.0189 | 0.0411 | 0.0625 |
| sep | 140 | 0.0024 | 0.0071 | 0.0184 | 0.0401 | 0.0504 |
| sep+add | 140 | -0.0105 | 0.0016 | 0.0140 | 0.0399 | 0.0540 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9857142857142858, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
| L5b-D013 sep+add recall@1 >= sep - 0.01 | yes | FAIL | [0.8571428571428571, 0.7] |
| L5b-D013 sep+add recall@5 >= sep - 0.005 | no | PASS | [1.0, 1.0] |
| L5b-D013 sep+add noise share <= 0.155 | no | FAIL | 0.20142857142857143 |
| L5b-D013 sep+add critical+hot above target <= 5 | no | FAIL | 46 |
| L5b-D013 kw-fix recall@1 (report only) | no | PASS | 0.7714285714285715 |
