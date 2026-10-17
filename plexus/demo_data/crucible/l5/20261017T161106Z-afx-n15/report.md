# Crucible L5 results

Run 2026-10-17T16:11:06Z, code df7333f, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1094 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 77.1% | 97.1% | 98.6% | 97.5% | 100.0% | 100.0% | 29.1% | 332 | - | 35 | 12 | 2.0% | n/a |
| sep+mult[w_entity=0.03;w_predicate=0.02] | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 19.9% | 308 | 0 | 20 | 0 | 0.0% | 3.97 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 1 | 1 | 41 | 4 | 0 |
| sep+mult[w_entity=0.03;w_predicate=0.02] | 0 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0020 | 0.0050 | 0.0171 | 0.0433 | 0.0654 |
| sep+mult[w_entity=0.03;w_predicate=0.02] | 140 | 0.0019 | 0.0060 | 0.0171 | 0.0417 | 0.0625 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
