# Crucible L5 results

Run 2026-10-17T13:08:04Z, code 2d0ec96, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 1051 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 75.7% | 97.1% | 98.6% | 97.5% | 100.0% | 100.0% | 23.4% | 323 | - | 36 | 13 | 0.0% | n/a |
| sep-entity | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 29.0% | 339 | 0 | 20 | 0 | 0.0% | 2.46 |
| sep[w_entity=0.03;w_predicate=0.02] | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 25.6% | 334 | 0 | 20 | 0 | 0.0% | 2.42 |
| sep+mult[w_entity=0.03;w_predicate=0.02] | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 20.7% | 310 | 0 | 20 | 0 | 0.0% | 2.47 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 2 | 0 | 42 | 5 | 0 |
| sep-entity | 0 | 0 | 20 | 0 | 0 |
| sep[w_entity=0.03;w_predicate=0.02] | 0 | 0 | 20 | 0 | 0 |
| sep+mult[w_entity=0.03;w_predicate=0.02] | 0 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0019 | 0.0044 | 0.0167 | 0.0504 | 0.0749 |
| sep-entity | 140 | 0.0024 | 0.0078 | 0.0254 | 0.0510 | 0.0769 |
| sep[w_entity=0.03;w_predicate=0.02] | 140 | 0.0024 | 0.0073 | 0.0239 | 0.0438 | 0.0676 |
| sep+mult[w_entity=0.03;w_predicate=0.02] | 140 | 0.0024 | 0.0078 | 0.0250 | 0.0443 | 0.0776 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
