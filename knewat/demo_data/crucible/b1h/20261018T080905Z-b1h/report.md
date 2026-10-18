# Crucible B1h: hand-written SQL on L2 and L2-scale (20261018T080905Z-b1h)

## L2 (43 questions)

B1h: **43/43 (100.0%)**; median 0.0 ms, p95 0.1 ms per question; 0 LLM calls.

| Family | correct |
|---|---|
| Decision provenance | 6/6 |
| Handoffs | 5/5 |
| Time travel | 5/5 |
| Supersession impact | 4/4 |
| Dependencies | 5/5 |
| Contradictions | 3/3 |
| Recovery | 4/4 |
| Memory currency and scope | 5/5 |
| Cross-session recall | 3/3 |
| Forgetting | 3/3 |

Wrong: none

Paired with the committed P rows: {"both_correct": 43, "b1h_only": 0, "p_only": 0, "both_wrong": 0, "n": 43}

## L2-scale (36 questions)

B1h: **36/36 (100.0%)**; median 0.1 ms, p95 1.7 ms per question; 0 LLM calls.

| Family | correct |
|---|---|
| Decision provenance | 4/4 |
| Handoffs | 4/4 |
| Time travel | 3/3 |
| Supersession impact | 4/4 |
| Dependencies | 3/3 |
| Contradictions | 4/4 |
| Recovery | 3/3 |
| Memory currency and scope | 4/4 |
| Cross-session recall | 3/3 |
| Forgetting | 4/4 |

Wrong: none

Paired with the committed P rows: {"both_correct": 36, "b1h_only": 0, "p_only": 0, "both_wrong": 0, "n": 36}

## Honesty

- B1h is the existing B1 SQLite store with one added table (claims, written in the claim's own transaction) because B1 never kept the claim history that the Recovery questions need and Knewat keeps as CLAIMED edges. No other schema or index change.
- The 17 SQL operations were written by the same author as the Cypher ones, with knowledge of the question set and the scenario: that is the point of a control (same effort, same spec), but it is not a blind SQL arm. Ground truth is the committed question files (derived from the script ledger), the ledger of the B1h replay equals the reference ledger.
- A tie on correctness here says the L2/L2-scale gap between Knewat and the B1/B0 readers is reader-vs-query, not graph-vs-SQL. B1h is in-process SQLite (no network hop), Knewat crosses a container network: latency columns are not a like-for-like speed comparison.
