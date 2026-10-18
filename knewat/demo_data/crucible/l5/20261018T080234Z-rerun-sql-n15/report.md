# Crucible L5 results

Run 2026-10-18T08:02:34Z, code 7f28f60, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 900 noise facts (15 per subject), 90 simulated days, 1096 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 80.7% | 98.6% | 99.3% | 98.8% | 100.0% | 100.0% | 46.3% | 378 | - | 33 | 6 | 0.0% | n/a |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 44.4% | 378 | 0 | 23 | 0 | 0.0% | 3.25 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 4 | 0 | 31 | 4 | 0 |
| sep+mult | 3 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0043 | 0.0082 | 0.0187 | 0.0366 | 0.0593 |
| sep+mult | 140 | 0.0035 | 0.0102 | 0.0201 | 0.0386 | 0.0596 |

## L5b SQL arm (B1h-L5, plan §5.4): Knewat vs hand-written SQL on the exported graph

SQLite 3.53.1 + sqlite-vec; export 2.17 s, rows {'scopes': 41, 'entities': 40, 'facts': 1080, 'fact_events': 3783, 'fact_decisions': 160, 'fact_links': 260, 'sources': 160}; SQL written for the arm: 92 non-blank non-comment lines (3 statements). Activation fidelity (SQL vs graph, every fact): 0 disagreements of 1080 (worst |gap| 0.00e+00).

| Mode | Arm | recall@1 | recall@3 | recall@5 | noise share | probe ms p50 | server/stmt ms p50 | statements / probe |
|---|---|---|---|---|---|---|---|---|
| off | Knewat | 80.7% | 98.6% | 99.3% | 46.3% | 101.69 | 36.04 | 2.00 |
| off | B1h-L5 (SQL) | 75.0% | 96.4% | 98.6% | 34.6% | 20.66 | 14.17 | 1.00 |
| sep+mult | Knewat | 85.7% | 100.0% | 100.0% | 44.4% | 193.01 | 63.22 | 6.00 |
| sep+mult | B1h-L5 (SQL) | 85.7% | 100.0% | 100.0% | 24.4% | 61.53 | 39.97 | 3.00 |

Paired per probe (same probes, same graph):

| Mode | n | only Knewat @1 | only SQL @1 | only Knewat @5 | only SQL @5 | same top-1 | identical top-5 list |
|---|---|---|---|---|---|---|---|
| off | 140 | 16 | 8 | 1 | 0 | 114 | 8 |
| sep+mult | 140 | 4 | 4 | 0 | 0 | 132 | 2 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 1080/1080.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
