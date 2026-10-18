# Crucible L7 family I: atomic multi-entity writes (full, run 20261016T100730Z-i)

## I1 writer crash (hard kill 0-400 ms after ready)

| arm | kills | started | acked | partial | lost acked | in flight at kill (complete/partial/absent) | partial per ack | r3 95% upper per kill |
|---|---|---|---|---|---|---|---|---|
| S-txn | 200 | 40163 | 40013 | 0 | 0 | 150 (77/0/73) | 0.0 | 0.015 |
| S-auto | 200 | 54084 | 53910 | 143 | 0 | 174 (11/143/20) | 0.002653 | - |

