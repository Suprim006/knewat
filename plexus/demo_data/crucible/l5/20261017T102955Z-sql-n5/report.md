# Crucible L5 results

Run 2026-10-17T10:29:55Z, code 0111b3a, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 727 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 75.0% | 96.4% | 98.6% | 97.5% | 100.0% | 100.0% | 27.4% | 331 | - | 39 | 13 | 0.0% | n/a |
| sep+mult | 82.9% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 20.9% | 309 | 0 | 24 | 0 | 0.0% | 2.39 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 5 | 3 | 42 | 2 | 0 |
| sep+mult | 0 | 3 | 21 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0019 | 0.0044 | 0.0167 | 0.0505 | 0.0709 |
| sep+mult | 140 | 0.0019 | 0.0071 | 0.0222 | 0.0436 | 0.0758 |

## L5b SQL arm (B1h-L5, plan §5.4): Plexus vs hand-written SQL on the exported graph

SQLite 3.53.1 + sqlite-vec; export 0.64 s, rows {'scopes': 41, 'entities': 40, 'facts': 480, 'fact_events': 2814, 'fact_decisions': 160, 'fact_links': 260, 'sources': 160}; SQL written for the arm: 92 non-blank non-comment lines (3 statements). Activation fidelity (SQL vs graph, every fact): 0 disagreements of 480 (worst |gap| 0.00e+00).

| Mode | Arm | recall@1 | recall@3 | recall@5 | noise share | probe ms p50 | server/stmt ms p50 | statements / probe |
|---|---|---|---|---|---|---|---|---|
| off | Plexus | 75.0% | 96.4% | 98.6% | 27.4% | 13.92 | 1.97 | 2.00 |
| off | B1h-L5 (SQL) | 75.7% | 96.4% | 98.6% | 27.0% | 13.25 | 6.78 | 1.00 |
| sep+mult | Plexus | 82.9% | 100.0% | 100.0% | 20.9% | 30.55 | 6.64 | 4.00 |
| sep+mult | B1h-L5 (SQL) | 82.9% | 100.0% | 100.0% | 20.4% | 17.78 | 10.75 | 3.00 |

Paired per probe (same probes, same graph):

| Mode | n | only Plexus @1 | only SQL @1 | only Plexus @5 | only SQL @5 | same top-1 | identical top-5 list |
|---|---|---|---|---|---|---|---|
| off | 140 | 0 | 1 | 0 | 0 | 139 | 136 |
| sep+mult | 140 | 3 | 3 | 0 | 0 | 134 | 127 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
