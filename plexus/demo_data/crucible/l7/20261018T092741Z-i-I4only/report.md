# Crucible L7 family I: atomic multi-entity writes (full, run 20261018T092741Z-i)

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
| FalkorDB | cas | 200 | 50 | 10000 | 4570 | 4568 | 2 | 5346 | 218517 |
| FalkorDB | pessimistic | 200 | 50 | 10000 | 3557 | 3556 | 1 | 27 | 212486 |

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

