# Crucible L5 results

Run 2026-10-17T08:24:49Z, code 3017ad7, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 1051 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 75.0% | 95.7% | 98.6% | 97.5% | 100.0% | 100.0% | 24.3% | 324 | - | 41 | 13 | 0.0% | n/a |
| on-mult | 63.6% | 91.4% | 95.0% | 97.5% | 100.0% | 90.2% | 14.4% | 278 | 0 | 47 | 52 | 3.9% | n/a |
| kw-fix | 76.4% | 97.9% | 98.6% | 97.5% | 100.0% | 100.0% | 14.4% | 280 | 0 | 29 | 16 | 0.0% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 24.6% | 325 | 0 | 20 | 0 | 0.0% | 2.29 |
| sep+add | 70.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 21.3% | 312 | 0 | 41 | 1 | 0.0% | 2.42 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 7 | 0 | 42 | 5 | 0 |
| on-mult | 0 | 4 | 95 | 0 | 0 |
| kw-fix | 0 | 2 | 43 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+add | 0 | 0 | 42 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0019 | 0.0044 | 0.0167 | 0.0455 | 0.0735 |
| on-mult | 140 | -0.0022 | 0.0036 | 0.0264 | 0.0411 | 0.0758 |
| kw-fix | 140 | 0.0014 | 0.0044 | 0.0207 | 0.0411 | 0.0758 |
| sep | 140 | 0.0024 | 0.0078 | 0.0262 | 0.0431 | 0.0678 |
| sep+add | 140 | -0.0119 | -0.0009 | 0.0167 | 0.0409 | 0.0724 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [0.9857142857142858, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
| L5b-D013 sep+add recall@1 >= sep - 0.01 | yes | FAIL | [0.8571428571428571, 0.7] |
| L5b-D013 sep+add recall@5 >= sep - 0.005 | no | PASS | [1.0, 1.0] |
| L5b-D013 sep+add noise share <= 0.155 | no | FAIL | 0.21285714285714286 |
| L5b-D013 sep+add critical+hot above target <= 5 | no | FAIL | 42 |
| L5b-D013 burst: hot above cold target <= 1% (sep+add) | no | PASS | 0.0 |
| L5b-D013 kw-fix recall@1 (report only) | no | PASS | 0.7642857142857142 |
