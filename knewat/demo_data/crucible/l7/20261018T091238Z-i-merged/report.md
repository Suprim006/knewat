# Crucible L7 family I: atomic multi-entity writes (full, run 20261018T091238Z-i-merged)

## I1 writer crash (hard kill 0-400 ms after ready)

| arm | kills | started | acked | partial | lost acked | in flight at kill (complete/partial/absent) | partial per ack | r3 95% upper per kill |
|---|---|---|---|---|---|---|---|---|
| S-txn | 200 | 18927 | 18776 | 0 | 0 | 151 (102/0/49) | 0.0 | 0.015 |
| S-auto | 200 | 22133 | 21957 | 142 | 0 | 176 (14/142/20) | 0.006467 | - |
| F-product | 200 | 123 | 24 | 52 | 0 | 99 (7/52/40) | 2.166667 | - |
| F-multi | 200 | 478 | 314 | 141 | 0 | 164 (23/141/0) | 0.449045 | - |
| F-multiexec | 200 | 1008 | 881 | 0 | 0 | 127 (124/0/3) | 0.0 | 0.015 |
| F-1stmt | 200 | 988 | 862 | 0 | 0 | 126 (125/0/1) | 0.0 | 0.015 |

## I2 logical abort (25% stale versions)

| arm | closeouts | stale | stale partial | stale absent | task mutated | leftover items | fresh complete | fresh partial | errors |
|---|---|---|---|---|---|---|---|---|---|
| S-txn | 400 | 103 | 0 | 103 | 0 | 0 | 297/297 | 0 | 0 |
| S-auto | 400 | 103 | 103 | 0 | 0 | 824 | 297/297 | 0 | 0 |
| F-product | 400 | 103 | 103 | 0 | 0 | 824 | 297/297 | 0 | 0 |
| F-multi | 400 | 103 | 103 | 0 | 0 | 824 | 297/297 | 0 | 0 |
| F-multi-cas-first | 400 | 103 | 0 | 103 | 0 | 0 | 297/297 | 0 | 0 |
| F-multiexec | 400 | 103 | 103 | 0 | 0 | 1339 | 297/297 | 0 | 0 |
| F-multiexec-err | 400 | 103 | 103 | 0 | 0 | 1339 | 297/297 | 0 | 0 |
| F-1stmt-first | 400 | 103 | 0 | 103 | 0 | 0 | 297/297 | 0 | 0 |
| F-1stmt-last | 400 | 103 | 0 | 103 | 0 | 0 | 297/297 | 0 | 0 |

## I3 database-server crash (`docker kill -s KILL`, 4 writers)

| arm | kills | started | acked | partial | lost acked | in flight (complete/partial/absent) | restart ready s p50 | failed restarts |
|---|---|---|---|---|---|---|---|---|
| F-1stmt | 20 | 1691 | 1639 | 0 | 0 | 52 (0/0/52) | 2.33 | 0 |
| F-multi | 20 | 895 | 829 | 61 | 4 | 66 (0/57/9) | 5.56 | 0 |

AOF replay reproduction: {"attempts": 3, "crashed": 2, "signatures": ["crashed by signal: 11, si_code: 1"]}

## I4a lost update (one counter)

| backend | mode | W | ops/writer | attempted | acked | final | lost (acked-final) | errors | retries |
|---|---|---|---|---|---|---|---|---|---|
| SQLite | naive | 20 | 50 | 1000 | 1000 | 89 | 911 | 0 | 0 |
| SQLite | atomic | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 0 |
| SQLite | cas | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 10 |
| SQLite | pessimistic | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 0 |
| FalkorDB | naive | 20 | 50 | 1000 | 1000 | 88 | 912 | 0 | 0 |
| FalkorDB | atomic | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 0 |
| FalkorDB | cas | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 8551 |
| FalkorDB | pessimistic | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 10265 |
| SQLite | naive | 200 | 50 | 10000 | 10000 | 128 | 9872 | 0 | 0 |
| SQLite | atomic | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 0 |
| SQLite | cas | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 90746 |
| SQLite | pessimistic | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 0 |
| FalkorDB | naive | 200 | 50 | 10000 | 10000 | 112 | 9888 | 0 | 0 |
| FalkorDB | atomic | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 0 |
| FalkorDB | cas | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 510102 |
| FalkorDB | pessimistic | 200 | 50 | 10000 | 9955 | 9955 | 0 | 45 | 576604 |

## I4b write skew

| backend | mode | think ms | rounds | violations | errors | claimed-both | claimed-none |
|---|---|---|---|---|---|---|---|
| SQLite | one statement | 0 | 500 | 0 | 0 | 0 | 0 |
| FalkorDB | one statement | 0 | 500 | 0 | 0 | 0 | 0 |
| SQLite | multi-statement no txn | 0 | 500 | 390 | 0 | 390 | 0 |
| SQLite | multi-statement no txn | 2 | 500 | 499 | 0 | 499 | 0 |
| FalkorDB | multi-statement no txn | 0 | 500 | 498 | 0 | 498 | 0 |
| FalkorDB | multi-statement no txn | 2 | 500 | 499 | 0 | 499 | 0 |
| SQLite | BEGIN IMMEDIATE | 0 | 500 | 0 | 0 | 0 | 0 |
| SQLite | BEGIN IMMEDIATE | 2 | 500 | 0 | 0 | 0 | 0 |
| SQLite | BEGIN DEFERRED | 0 | 500 | 0 | 424 | 0 | 0 |
| SQLite | BEGIN DEFERRED | 2 | 500 | 0 | 498 | 0 | 0 |
| FalkorDB | WATCH+MULTI/EXEC | 0 | 500 | 0 | 0 | 0 | 0 |
| FalkorDB | WATCH+MULTI/EXEC | 2 | 500 | 0 | 0 | 0 | 0 |

## I5 single-statement sufficiency

* statement lines: {'F-1stmt': 14, 'S-txn': 12}; python glue (closeout method): {'F-1stmt': 12, 'S-txn': 27}
* statements per close-out: {'F-1stmt': 1, 'S-txn': 13}

| arm | writers | p50 ms | p99 ms | closeouts/s | round trips | errors |
|---|---|---|---|---|---|---|
| F-1stmt | 1 | 5.355 | 32.484 | 88.8 | 1 | 0 |
| F-1stmt | 8 | 117.986 | 252.05 | 37.6 | 1 | 0 |
| S-txn | 1 | 0.413 | 7.419 | 1255.3 | 13 | 0 |
| S-txn | 8 | 0.453 | 9.635 | 1059.7 | 13 | 0 |

S-txn: embedded (in-process SQLite, no network); F-1stmt: server (Docker port-forward)
