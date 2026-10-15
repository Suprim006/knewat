# Crucible L5 results

Run 2026-10-15T20:27:26Z, code 75bd122, embedder FastEmbedder, LLM calls: 0.
Design, hypotheses and pass criteria: `docs/BASELINE.md`, "L5 pre-registration".

## L5a: staleness

12 modules, 60 functions/facts, 20 change commits (docstring, add, docstring, docstring, value, add, module-comment, value, whitespace, module-comment, value, sibling, delete, reorder, reorder, docstring, sibling, delete, module-comment, value); 19 (commit, fact) pairs changed in total.

| Arm | TP | FP | FN | precision | recall | stale returned unflagged | stale not in top 3 |
|---|---|---|---|---|---|---|---|
| S symbol-level anchors | 19 | 0 | 0 | 100.0% | 100.0% | 0 | 0 |
| F file-level anchors | 19 | 106 | 0 | 15.2% | 100.0% | 0 | 0 |
| N no anchors (baseline) | 0 | 0 | 19 | n/a | 0.0% | 19 | 0 |

Facts flagged per edit kind (all arms):

| Kind | S | F | N |
|---|---|---|---|
| docstring | 4 | 20 | 0 |
| add | 0 | 10 | 0 |
| value | 9 | 45 | 0 |
| module-comment | 0 | 15 | 0 |
| whitespace | 0 | 5 | 0 |
| sibling | 4 | 10 | 0 |
| delete | 2 | 10 | 0 |
| reorder | 0 | 10 | 0 |

## L5b: forgetting

20 sprints, 140 real active facts (critical 80, hot 9, cold 51), 300 noise facts (5 per subject), 90 simulated days, 739 simulated READ edges.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | hot@5 | cold@5 | noise share | chars / recall | critical loss |
|---|---|---|---|---|---|---|---|---|---|
| off | 75.7% | 97.1% | 98.6% | 97.5% | 100.0% | 100.0% | 23.0% | 322 | - |
| on | 22.1% | 45.0% | 72.9% | 87.5% | 100.0% | 45.1% | 10.0% | 256 | 8 |
| on+sweep | 12.9% | 42.9% | 67.9% | 85.0% | 100.0% | 35.3% | 4.7% | 245 | 10 |

Sweep (real, `on+sweep`): 188 facts moved to dormant: {'critical': 0, 'hot': 0, 'cold_real': 16, 'noise': 172}; critical facts among the dry-run candidates: 0; Fact nodes before/after: 480/480.

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5a unflagged = 0 (S) | yes | PASS | 0 |
| L5a unflagged = 0 (F) | yes | PASS | 0 |
| L5b critical-probe loss = 0 (on, on+sweep) | yes | FAIL | [8, 10] |
| L5b no critical fact moved to dormant | yes | PASS | 0 |
| L5b fact count unchanged by the sweep | yes | PASS | [480, 480] |
| L5b recall@5 of 'on' within 0.02 of 'off' | no | FAIL | [0.9857142857142858, 0.7285714285714285] |
| L5b noise share reduced | no | PASS | [0.23, 0.047142857142857146] |
