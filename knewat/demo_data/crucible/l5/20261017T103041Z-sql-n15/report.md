# Crucible L5 results

Run 2026-10-17T10:30:41Z, code 0111b3a, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1096 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 75.7% | 97.1% | 97.9% | 96.2% | 100.0% | 100.0% | 31.7% | 340 | - | 38 | 13 | 0.0% | n/a |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 19.1% | 305 | 0 | 20 | 0 | 0.0% | 2.63 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 4 | 1 | 42 | 4 | 0 |
| sep+mult | 0 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0019 | 0.0040 | 0.0171 | 0.0480 | 0.0727 |
| sep+mult | 140 | 0.0019 | 0.0071 | 0.0222 | 0.0401 | 0.0625 |

## L5b SQL arm (B1h-L5, plan §5.4): Knewat vs hand-written SQL on the exported graph

SQLite 3.53.1 + sqlite-vec; export 1.25 s, rows {'scopes': 41, 'entities': 40, 'facts': 1080, 'fact_events': 3783, 'fact_decisions': 160, 'fact_links': 260, 'sources': 160}; SQL written for the arm: 92 non-blank non-comment lines (3 statements). Activation fidelity (SQL vs graph, every fact): 0 disagreements of 1080 (worst |gap| 0.00e+00).

| Mode | Arm | recall@1 | recall@3 | recall@5 | noise share | probe ms p50 | server/stmt ms p50 | statements / probe |
|---|---|---|---|---|---|---|---|---|
| off | Knewat | 75.7% | 97.1% | 97.9% | 31.7% | 15.06 | 2.66 | 2.00 |
| off | B1h-L5 (SQL) | 75.7% | 97.1% | 97.9% | 31.6% | 20.45 | 14.00 | 1.00 |
| sep+mult | Knewat | 85.7% | 100.0% | 100.0% | 19.1% | 29.73 | 7.14 | 4.00 |
| sep+mult | B1h-L5 (SQL) | 85.7% | 100.0% | 100.0% | 19.1% | 26.49 | 19.54 | 3.00 |

Paired per probe (same probes, same graph):

| Mode | n | only Knewat @1 | only SQL @1 | only Knewat @5 | only SQL @5 | same top-1 | identical top-5 list |
|---|---|---|---|---|---|---|---|
| off | 140 | 0 | 0 | 0 | 0 | 140 | 139 |
| sep+mult | 140 | 3 | 3 | 0 | 0 | 134 | 124 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
