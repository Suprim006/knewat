# Crucible L7 family I: atomic multi-entity writes (full, run 20261018T092741Z-i)

## I1 writer crash (hard kill 0-400 ms after ready)

| arm | kills | started | acked | partial | lost acked | in flight at kill (complete/partial/absent) | partial per ack | r3 95% upper per kill |
|---|---|---|---|---|---|---|---|---|
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

