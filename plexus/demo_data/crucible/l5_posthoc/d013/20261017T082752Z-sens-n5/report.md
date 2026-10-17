# Crucible L5 results

Run 2026-10-17T08:27:52Z, code 3017ad7, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 739 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 75.7% | 97.1% | 98.6% | 97.5% | 100.0% | 100.0% | 23.9% | 325 | - | 36 | 13 | 0.0% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 24.1% | 326 | 0 | 20 | 0 | 0.0% | 2.57 |
| sep+mult | 85.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 22.1% | 313 | 0 | 21 | 0 | 0.0% | 2.35 |
| sep+add | 70.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 23.6% | 318 | 0 | 41 | 1 | 0.0% | 2.49 |
| sep+add[delta=0] | 70.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 23.6% | 318 | 0 | 41 | 0 | 0.0% | 2.44 |
| sep+add[beta=0.01] | 72.9% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 23.9% | 321 | 0 | 37 | 1 | 0.0% | 2.38 |
| sep+add[beta=0.01;delta=0] | 85.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 23.9% | 321 | 0 | 21 | 0 | 0.0% | 2.48 |
| sep+add[beta=0.01;delta=0.01;band=0.005] | 85.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 23.9% | 321 | 0 | 21 | 0 | 0.0% | 2.30 |
| sep+add[beta=0.02;delta=0] | 80.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 23.9% | 320 | 0 | 27 | 0 | 0.0% | 2.41 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 2 | 1 | 42 | 4 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 0 | 0 | 21 | 0 | 0 |
| sep+add | 0 | 0 | 42 | 0 | 0 |
| sep+add[delta=0] | 0 | 0 | 41 | 0 | 0 |
| sep+add[beta=0.01] | 0 | 0 | 38 | 0 | 0 |
| sep+add[beta=0.01;delta=0] | 0 | 0 | 21 | 0 | 0 |
| sep+add[beta=0.01;delta=0.01;band=0.005] | 0 | 0 | 21 | 0 | 0 |
| sep+add[beta=0.02;delta=0] | 0 | 0 | 27 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0019 | 0.0044 | 0.0167 | 0.0482 | 0.0739 |
| sep | 140 | 0.0025 | 0.0078 | 0.0262 | 0.0436 | 0.0673 |
| sep+mult | 140 | 0.0024 | 0.0073 | 0.0254 | 0.0443 | 0.0753 |
| sep+add | 140 | -0.0119 | -0.0009 | 0.0167 | 0.0431 | 0.0707 |
| sep+add[delta=0] | 140 | -0.0119 | -0.0019 | 0.0239 | 0.0448 | 0.0724 |
| sep+add[beta=0.01] | 140 | -0.0105 | 0.0029 | 0.0222 | 0.0423 | 0.0625 |
| sep+add[beta=0.01;delta=0] | 140 | 0.0024 | 0.0078 | 0.0262 | 0.0436 | 0.0673 |
| sep+add[beta=0.01;delta=0.01;band=0.005] | 140 | 0.0024 | 0.0078 | 0.0254 | 0.0436 | 0.0673 |
| sep+add[beta=0.02;delta=0] | 140 | -0.0014 | 0.0054 | 0.0254 | 0.0436 | 0.0673 |

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
| L5b-D013 sep+add noise share <= 0.155 | no | FAIL | 0.2357142857142857 |
| L5b-D013 sep+add critical+hot above target <= 5 | no | FAIL | 42 |
