# Crucible L7 family I: atomic multi-entity writes (full, run 20261018T101537Z-i)

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
