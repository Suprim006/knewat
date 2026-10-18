# Crucible L7 family I: atomic multi-entity writes (full, run 20261018T094400Z-i)

## I3 database-server crash (`docker kill -s KILL`, 4 writers)

| arm | kills | started | acked | partial | lost acked | in flight (complete/partial/absent) | restart ready s p50 | failed restarts |
|---|---|---|---|---|---|---|---|---|
| F-1stmt | 20 | 1691 | 1639 | 0 | 0 | 52 (0/0/52) | 2.33 | 0 |
| F-multi | 20 | 895 | 829 | 61 | 4 | 66 (0/57/9) | 5.56 | 0 |

