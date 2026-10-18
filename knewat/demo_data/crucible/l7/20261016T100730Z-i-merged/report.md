# Crucible L7 family I: atomic multi-entity writes (full, run 20261016T100730Z-i-merged)

## I1 writer crash (hard kill 0-400 ms after ready)

| arm | kills | started | acked | partial | lost acked | in flight at kill (complete/partial/absent) | partial per ack | r3 95% upper per kill |
|---|---|---|---|---|---|---|---|---|
| S-txn | 200 | 40163 | 40013 | 0 | 0 | 150 (77/0/73) | 0.0 | 0.015 |
| S-auto | 200 | 54084 | 53910 | 143 | 0 | 174 (11/143/20) | 0.002653 | - |
| F-product | 200 | 365 | 230 | 86 | 0 | 135 (13/86/36) | 0.373913 | - |
| F-multi | 200 | 1783 | 1617 | 145 | 0 | 166 (20/145/1) | 0.089672 | - |
| F-multiexec | 200 | 2704 | 2546 | 0 | 0 | 158 (155/0/3) | 0.0 | 0.015 |
| F-1stmt | 200 | 3198 | 3055 | 0 | 0 | 143 (141/0/2) | 0.0 | 0.015 |

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
| F-1stmt | 20 | 2974 | 2930 | 0 | 0 | 44 (0/0/44) | 9.51 | 0 |
| F-multi | 20 | 2473 | 2412 | 52 | 0 | 61 (0/52/9) | 10.75 | 0 |

AOF replay reproduction: {"attempts": 3, "crashed": 3, "signatures": ["Guru Meditation: illegal decrRefCount for object with: type 0, encoding 8, refcount 0 #object.c:648", "crashed by signal: 11, si_code: 1"]}

## I4a lost update (one counter)

| backend | mode | W | ops/writer | attempted | acked | final | lost (acked-final) | errors | retries |
|---|---|---|---|---|---|---|---|---|---|
| SQLite | naive | 20 | 50 | 1000 | 1000 | 102 | 898 | 0 | 0 |
| SQLite | atomic | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 0 |
| SQLite | cas | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 106 |
| SQLite | pessimistic | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 0 |
| FalkorDB | naive | 20 | 50 | 1000 | 1000 | 88 | 912 | 0 | 0 |
| FalkorDB | atomic | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 0 |
| FalkorDB | cas | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 6331 |
| FalkorDB | pessimistic | 20 | 50 | 1000 | 1000 | 1000 | 0 | 0 | 8180 |
| SQLite | naive | 200 | 50 | 10000 | 10000 | 195 | 9805 | 0 | 0 |
| SQLite | atomic | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 0 |
| SQLite | cas | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 111292 |
| SQLite | pessimistic | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 0 |
| FalkorDB | naive | 200 | 50 | 10000 | 10000 | 103 | 9897 | 0 | 0 |
| FalkorDB | atomic | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 0 |
| FalkorDB | cas | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 284541 |
| FalkorDB | pessimistic | 200 | 50 | 10000 | 10000 | 10000 | 0 | 0 | 437463 |

## I4b write skew

| backend | mode | think ms | rounds | violations | errors | claimed-both | claimed-none |
|---|---|---|---|---|---|---|---|
| SQLite | one statement | 0 | 500 | 0 | 0 | 0 | 0 |
| FalkorDB | one statement | 0 | 500 | 0 | 0 | 0 | 0 |
| SQLite | multi-statement no txn | 0 | 500 | 485 | 0 | 485 | 0 |
| SQLite | multi-statement no txn | 2 | 500 | 500 | 0 | 500 | 0 |
| FalkorDB | multi-statement no txn | 0 | 500 | 499 | 0 | 499 | 0 |
| FalkorDB | multi-statement no txn | 2 | 500 | 499 | 0 | 499 | 0 |
| SQLite | BEGIN IMMEDIATE | 0 | 500 | 0 | 0 | 0 | 0 |
| SQLite | BEGIN IMMEDIATE | 2 | 500 | 0 | 0 | 0 | 0 |
| SQLite | BEGIN DEFERRED | 0 | 500 | 0 | 494 | 0 | 0 |
| SQLite | BEGIN DEFERRED | 2 | 500 | 0 | 500 | 0 | 0 |
| FalkorDB | WATCH+MULTI/EXEC | 0 | 500 | 0 | 0 | 0 | 0 |
| FalkorDB | WATCH+MULTI/EXEC | 2 | 500 | 0 | 0 | 0 | 0 |

## I5 single-statement sufficiency

* statement lines: {'F-1stmt': 14, 'S-txn': 12}; python glue (closeout method): {'F-1stmt': 12, 'S-txn': 27}
* statements per close-out: {'F-1stmt': 1, 'S-txn': 13}

| arm | writers | p50 ms | p99 ms | closeouts/s | round trips | errors |
|---|---|---|---|---|---|---|
| F-1stmt | 1 | 3.4 | 4.694 | 169.8 | 1 | 0 |
| F-1stmt | 8 | 35.42 | 82.681 | 112.5 | 1 | 0 |
| S-txn | 1 | 0.19 | 5.219 | 2511.4 | 13 | 0 |
| S-txn | 8 | 0.222 | 6.376 | 2001.8 | 13 | 0 |

S-txn: embedded (in-process SQLite, no network); F-1stmt: server (Docker port-forward)
