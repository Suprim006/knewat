# Crucible L7 family I: atomic multi-entity writes (full, run 20261018T092740Z-i)

## I1 writer crash (hard kill 0-400 ms after ready)

| arm | kills | started | acked | partial | lost acked | in flight at kill (complete/partial/absent) | partial per ack | r3 95% upper per kill |
|---|---|---|---|---|---|---|---|---|
| F-product | 200 | 123 | 24 | 52 | 0 | 99 (7/52/40) | 2.166667 | - |

