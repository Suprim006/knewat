# Crucible L5 results

Run 2026-10-18T07:46:46Z, code 7f28f60, embedder FastEmbedder, LLM calls: 0.
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

## Pass criteria (fixed in the pre-registration)

| Criterion | hard | result | value |
|---|---|---|---|
| L5a unflagged = 0 (S) | yes | PASS | 0 |
| L5a unflagged = 0 (F) | yes | PASS | 0 |
