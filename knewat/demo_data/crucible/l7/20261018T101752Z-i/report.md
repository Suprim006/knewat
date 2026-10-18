# Crucible L7 family I: atomic multi-entity writes (full, run 20261018T101752Z-i)

## I3 database-server crash (`docker kill -s KILL`, 4 writers)

| arm | kills | started | acked | partial | lost acked | in flight (complete/partial/absent) | restart ready s p50 | failed restarts |
|---|---|---|---|---|---|---|---|---|
| F-1stmt | 20 | 2307 | 2263 | 0 | 22 | 44 (0/0/44) | 16.42 | 0 |
| F-multi | 20 | 1908 | 1847 | 53 | 0 | 61 (0/53/8) | 8.3 | 0 |

