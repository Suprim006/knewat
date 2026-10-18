# Crucible L5 results

Run 2026-10-18T08:05:31Z, code 7f28f60, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 1051 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss | above same entity | above other entity | hot above cold | entity read ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| off | 78.6% | 98.6% | 99.3% | 98.8% | 100.0% | 100.0% | 29.4% | 345 | - | 32 | 8 | 0.0% | n/a |
| sep+mult | 85.7% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 33.3% | 353 | 0 | 21 | 0 | 0.0% | 2.88 |

Post-hoc diagnostic (added after the first run; not pre-registered): class of the rows ranked above the target (on a miss, of all rows returned), summed over all probes:

| Mode | noise | hot | critical | cold | other |
|---|---|---|---|---|---|
| off | 2 | 1 | 32 | 5 | 0 |
| sep+mult | 1 | 0 | 20 | 0 | 0 |

Relevance gap between the first and second returned row (cosine distance), per mode:

| Mode | n | p10 | p25 | p50 | p75 | p90 |
|---|---|---|---|---|---|---|
| off | 140 | 0.0045 | 0.0085 | 0.0192 | 0.0410 | 0.0682 |
| sep+mult | 140 | 0.0043 | 0.0102 | 0.0201 | 0.0410 | 0.0668 |

## L5b SQL arm (B1h-L5, plan §5.4): Plexus vs hand-written SQL on the exported graph

SQLite 3.53.1 + sqlite-vec; export 0.64 s, rows {'scopes': 41, 'entities': 40, 'facts': 480, 'fact_events': 3138, 'fact_decisions': 160, 'fact_links': 260, 'sources': 160}; SQL written for the arm: 92 non-blank non-comment lines (3 statements). Activation fidelity (SQL vs graph, every fact): 0 disagreements of 480 (worst |gap| 0.00e+00).

| Mode | Arm | recall@1 | recall@3 | recall@5 | noise share | probe ms p50 | server/stmt ms p50 | statements / probe |
|---|---|---|---|---|---|---|---|---|
| off | Plexus | 78.6% | 98.6% | 99.3% | 29.4% | 52.33 | 19.75 | 2.00 |
| off | B1h-L5 (SQL) | 75.7% | 97.1% | 98.6% | 23.4% | 12.86 | 6.49 | 1.00 |
| sep+mult | Plexus | 85.7% | 100.0% | 100.0% | 33.3% | 168.25 | 49.90 | 6.00 |
| sep+mult | B1h-L5 (SQL) | 84.3% | 100.0% | 100.0% | 22.0% | 19.10 | 11.22 | 3.00 |

Paired per probe (same probes, same graph):

| Mode | n | only Plexus @1 | only SQL @1 | only Plexus @5 | only SQL @5 | same top-1 | identical top-5 list |
|---|---|---|---|---|---|---|---|
| off | 140 | 13 | 9 | 1 | 0 | 115 | 15 |
| sep+mult | 140 | 7 | 5 | 0 | 0 | 128 | 10 |

Sweep (real, `on+sweep`): 0 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 0, 'noise': 0}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
