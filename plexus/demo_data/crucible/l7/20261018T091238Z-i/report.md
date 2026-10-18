# Crucible L7 family I: atomic multi-entity writes (full, run 20261018T091238Z-i)

## I1 writer crash (hard kill 0-400 ms after ready)

| arm | kills | started | acked | partial | lost acked | in flight at kill (complete/partial/absent) | partial per ack | r3 95% upper per kill |
|---|---|---|---|---|---|---|---|---|
| S-txn | 200 | 18927 | 18776 | 0 | 0 | 151 (102/0/49) | 0.0 | 0.015 |
| S-auto | 200 | 22133 | 21957 | 142 | 0 | 176 (14/142/20) | 0.006467 | - |

