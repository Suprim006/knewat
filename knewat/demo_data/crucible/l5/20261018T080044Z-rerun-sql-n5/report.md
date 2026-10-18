# Crucible L5 results

Run 2026-10-18T08:00:44Z, code 7f28f60, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 739 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 78.6% | 98.6% | 99.3% | 98.8% | 100.0% | 100.0% | 30.3% | 349 | - | 32 | 7 | 0.0% | n/a |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 32.6% | 355 | 0 | 24 | 0 | 0.0% | 4.45 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 1 | 0 | 32 | 6 | 0 |
| sep+mult | 4 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0045 | 0.0087 | 0.0187 | 0.0369 | 0.0689 |
| sep+mult | 140 | 0.0035 | 0.0102 | 0.0255 | 0.0420 | 0.0689 |

## L5b SQL arm (B1h-L5, plan §5.4): Plexus vs hand-written SQL on the exported graph

SQLite 3.53.1 + sqlite-vec; export 0.76 s, rows {'scopes': 41, 'entities': 40, 'facts': 480, 'fact_events': 2826, 'fact_decisions': 160, 'fact_links': 260, 'sources': 160}; SQL written for the arm: 92 non-blank non-comment lines (3 statements). Activation fidelity (SQL vs graph, every fact): 0 disagreements of 480 (worst |gap| 0.00e+00).

| Mode | Arm | recall@1 | recall@3 | recall@5 | noise share | probe ms p50 | server/stmt ms p50 | statements / probe |
|---|---|---|---|---|---|---|---|---|
| off | Plexus | 78.6% | 98.6% | 99.3% | 30.3% | 51.50 | 18.90 | 2.00 |
| off | B1h-L5 (SQL) | 75.7% | 97.1% | 98.6% | 23.9% | 13.13 | 6.57 | 1.00 |
| sep+mult | Plexus | 85.7% | 100.0% | 100.0% | 32.6% | 229.57 | 65.38 | 6.00 |
| sep+mult | B1h-L5 (SQL) | 85.0% | 100.0% | 100.0% | 22.4% | 64.23 | 28.24 | 3.00 |

Paired per probe (same probes, same graph):

| Mode | n | only Plexus @1 | only SQL @1 | only Plexus @5 | only SQL @5 | same top-1 | identical top-5 list |
|---|---|---|---|---|---|---|---|
| off | 140 | 13 | 9 | 1 | 0 | 115 | 19 |
| sep+mult | 140 | 6 | 5 | 0 | 0 | 129 | 11 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
