# Crucible L5 results

Run 2026-10-17T22:02:55Z, code 00ccc82, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 739 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 80.7% | 99.3% | 100.0% | 100.0% | 100.0% | 100.0% | 30.1% | 353 | - | 26 | 4 | 0.0% | n/a |
| sep | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 31.7% | 353 | 0 | 20 | 0 | 0.0% | 2.88 |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 32.4% | 356 | 0 | 21 | 0 | 0.0% | 3.41 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 1 | 1 | 27 | 1 | 0 |
| sep | 0 | 0 | 20 | 0 | 0 |
| sep+mult | 1 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0045 | 0.0090 | 0.0187 | 0.0402 | 0.0692 |
| sep | 140 | 0.0045 | 0.0094 | 0.0196 | 0.0412 | 0.0692 |
| sep+mult | 140 | 0.0050 | 0.0102 | 0.0211 | 0.0448 | 0.0797 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5b-D013 sep recall@1 >= 0.90 | no | FAIL | [0.8571428571428571] |
| L5b-D013 sep recall@1 >= 0.85 (falsification floor) | yes | PASS | [0.8571428571428571] |
| L5b-D013 sep recall@5 >= off - 0.005 | no | PASS | [1.0, 1.0] |
| L5b-D013 sep critical loss = 0 | yes | PASS | 0 |
