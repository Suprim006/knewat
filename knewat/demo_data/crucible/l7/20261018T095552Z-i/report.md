# Crucible L7 family I: atomic multi-entity writes (full, run 20261018T095552Z-i)

## I3 database-server crash (`docker kill -s KILL`, 4 writers)

| arm | kills | started | acked | partial | lost acked | in flight (complete/partial/absent) | restart ready s p50 | failed restarts |
|---|---|---|---|---|---|---|---|---|
| F-1stmt | 20 | 1741 | 1690 | 0 | 0 | 51 (0/0/51) | 10.48 | 0 |
| F-multi | 20 | 1266 | 1191 | 63 | 51 | 75 (0/61/14) | 11.0 | 0 |

