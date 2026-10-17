# Crucible L7 family I: atomic multi-entity writes (full, run 20261016T111433Z-i)

## I5 single-statement sufficiency

* statement lines: {'F-1stmt': 14, 'S-txn': 12}; python glue (closeout method): {'F-1stmt': 12, 'S-txn': 27}
* statements per close-out: {'F-1stmt': 1, 'S-txn': 13}

| arm | writers | p50 ms | p99 ms | closeouts/s | round trips | errors |
|---|---|---|---|---|---|---|
| F-1stmt | 1 | 3.44 | 5.895 | 168.4 | 1 | 0 |
| F-1stmt | 8 | 34.228 | 83.539 | 114.2 | 1 | 0 |
| S-txn | 1 | 0.194 | 5.074 | 2495.1 | 13 | 0 |
| S-txn | 8 | 0.218 | 6.284 | 1983.0 | 13 | 0 |

S-txn: embedded (in-process SQLite, no network); F-1stmt: server (Docker port-forward)
