# Crucible L5 results

Run 2026-10-17T21:47:28Z, code 9f50190, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1096 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 83.6% | 99.3% | 100.0% | 100.0% | 100.0% | 100.0% | 55.4% | 420 | - | 27 | 0 | 0.0% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 61.3% | 434 | 0 | 20 | 0 | 0.0% | 3.02 |
| sep+mult | 78.6% | 92.1% | 98.6% | 97.5% | 100.0% | 100.0% | 61.4% | 437 | 2 | 67 | 0 | 0.0% | 2.60 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 7 | 0 | 20 | 0 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 47 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0057 | 0.0141 | 0.0376 | 0.0644 | 0.0829 |
| sep | 140 | 0.0069 | 0.0145 | 0.0405 | 0.0710 | 0.0886 |
| sep+mult | 140 | 0.0015 | 0.0098 | 0.0530 | 0.0764 | 0.0897 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [1.0, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
