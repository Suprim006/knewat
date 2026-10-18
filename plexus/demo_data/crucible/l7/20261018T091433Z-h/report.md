# Crucible L7 family H: expressiveness and traversal (20261018T091433Z-h)

SQLite = embedded (in-process); FalkorDB = server (Docker port-forward). Lines = non-blank non-comment lines of the statement file; app lines = Python BFS lines (for `+app-bfs`).

## scale small: {'agents': 50, 'sources': 100, 'facts': 2061, 'fact_parents': 2900, 'fact_source': 769, 'steps': 1220, 'reads': 3007, 'decisions': 100, 'based_on': 206, 'handoffs': 90, 'carries': 114}

| question | arm | lines | app lines | statements (max) | strict | timeouts | errors | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| H1a | cypher h1a.cypher | 5 | 0 | 1 | 1/1 | 0 | 0 | 12.368 | 14.205 |
| H1a | sql h1a.sql | 12 | 0 | 1 | 1/1 | 0 | 0 | 9.938 | 14.788 |
| H1b | cypher h1b.cypher | 7 | 0 | 1 | 1/1 | 0 | 0 | 8.079 | 18.726 |
| H1b | sql h1b.sql | 20 | 0 | 1 | 1/1 | 0 | 0 | 0.295 | 1.37 |
| H1c | cypher h1c.cypher | 13 | 0 | 1 | 1/1 | 0 | 0 | 1492.504 | 1892.076 |
| H1c | sql h1c.sql | 20 | 0 | 1 | 1/1 | 0 | 0 | 132.135 | 279.503 |
| H2 | cypher h2.cypher | 6 | 0 | 1 | 24/24 | 0 | 0 | 38.122 | 224.285 |
| H2 | sql h2.sql | 14 | 0 | 1 | 24/24 | 0 | 0 | 0.213 | 9.483 |
| H1c | cypher h1c.natural.cypher | 7 | 0 | 0 | 0/1 | 0 | 1 | 5950.975 | 5950.975 |
| H4 | cypher h4.naive.cypher | 3 | 0 | 1 | 1/1 | 1 | 0 | 10000.0 | 10000.0 |
| H4 | cypher h4.distinct.cypher | 7 | 0 | 1 | 1/1 | 0 | 0 | 34.313 | 161.682 |
| H4 | cypher h4.bfs.cypher | 8 | 0 | 1 | 1/1 | 0 | 0 | 406.139 | 445.054 |
| H4 | sql h4.sql | 8 | 0 | 1 | 1/1 | 0 | 0 | 12.684 | 14.197 |
| H3 | cypher h3.varlen.cypher | 4 | 0 | 1 | 12/12 | 0 | 0 | 5.768 | 14.659 |
| H3 | cypher h3.varlen.cypher+unbounded | 4 | 0 | 1 | 12/12 | 0 | 0 | 16.854 | 76.51 |
| H3 | cypher h3.shortestpath.cypher | 4 | 0 | 1 | 8/12 | 0 | 0 | 3.783 | 18.863 |
| H3 | sql h3.path_cte.sql | 9 | 0 | 1 | 12/12 | 0 | 0 | 0.175 | 0.513 |
| H3 | sql h3.path_cte.sql+unbounded | 9 | 0 | 1 | 12/12 | 0 | 0 | 0.239 | 1.248 |
| H3 | sql h3.depth_cte.sql | 8 | 0 | 1 | 12/12 | 0 | 0 | 0.228 | 13.941 |
| H3 | cypher h3.bfs_level.cypher+app-bfs | 3 | 18 | 11 | 12/12 | 0 | 0 | 54.567 | 289.164 |
| H3 | sql h3.bfs_level.sql+app-bfs | 3 | 18 | 11 | 12/12 | 0 | 0 | 0.202 | 25.931 |

* H1c:cypher:h1c.natural.cypher: wrong on H1c(; ResponseError: Query's mem consumption exceeded capacity)
* H3:cypher:h3.shortestpath.cypher: wrong on H3-04(trap), H3-05(trap), H3-06(trap), H3-07(trap)

## scale large: {'agents': 200, 'sources': 1000, 'facts': 50061, 'fact_parents': 68068, 'fact_source': 18675, 'steps': 30500, 'reads': 75510, 'decisions': 2500, 'based_on': 4970, 'handoffs': 1650, 'carries': 2398}

| question | arm | lines | app lines | statements (max) | strict | timeouts | errors | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| H1a | cypher h1a.cypher | 5 | 0 | 1 | 1/1 | 0 | 0 | 260.002 | 307.717 |
| H1a | sql h1a.sql | 12 | 0 | 1 | 1/1 | 0 | 0 | 1689.008 | 1897.588 |
| H1b | cypher h1b.cypher | 7 | 0 | 1 | 1/1 | 0 | 0 | 120.85 | 124.733 |
| H1b | sql h1b.sql | 20 | 0 | 1 | 1/1 | 0 | 0 | 10.045 | 14.715 |
| H1c | cypher h1c.cypher | 13 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H1c | sql h1c.sql | 20 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H2 | cypher h2.cypher | 6 | 0 | 1 | 24/24 | 0 | 0 | 1613.464 | 3899.68 |
| H2 | sql h2.sql | 14 | 0 | 1 | 24/24 | 0 | 0 | 3.223 | 40.558 |
| H1c | cypher h1c.natural.cypher | 7 | 0 | 0 | 0/1 | 0 | 1 | 1859.912 | 1859.912 |
| H4 | cypher h4.naive.cypher | 3 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H4 | cypher h4.distinct.cypher | 7 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H4 | cypher h4.bfs.cypher | 8 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H4 | sql h4.sql | 8 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H3 | cypher h3.varlen.cypher | 4 | 0 | 1 | 12/12 | 0 | 0 | 6.397 | 29.69 |
| H3 | cypher h3.varlen.cypher+unbounded | 4 | 0 | 1 | 2/12 | 10 | 0 | 10000.0 | 10000.0 |
| H3 | cypher h3.shortestpath.cypher | 4 | 0 | 1 | 8/12 | 0 | 0 | 5.944 | 14.245 |
| H3 | sql h3.path_cte.sql | 9 | 0 | 1 | 12/12 | 0 | 0 | 0.49 | 43.581 |
| H3 | sql h3.path_cte.sql+unbounded | 9 | 0 | 1 | 12/12 | 0 | 0 | 1.052 | 28.625 |
| H3 | sql h3.depth_cte.sql | 8 | 0 | 1 | 12/12 | 0 | 0 | 0.33 | 1.702 |
| H3 | cypher h3.bfs_level.cypher+app-bfs | 3 | 18 | 25 | 12/12 | 0 | 0 | 36.733 | 208.101 |
| H3 | sql h3.bfs_level.sql+app-bfs | 3 | 18 | 25 | 12/12 | 0 | 0 | 0.384 | 3.7 |

* H1c:cypher:h1c.cypher: wrong on H1c(; timeout)
* H1c:sql:h1c.sql: wrong on H1c(; timeout)
* H1c:cypher:h1c.natural.cypher: wrong on H1c(; ResponseError: Query's mem consumption exceeded capacity)
* H4:cypher:h4.naive.cypher: wrong on H4(; timeout)
* H4:cypher:h4.distinct.cypher: wrong on H4(; timeout)
* H4:cypher:h4.bfs.cypher: wrong on H4(; timeout)
* H4:sql:h4.sql: wrong on H4(; timeout)
* H3:cypher:h3.varlen.cypher+unbounded: wrong on H3-00(plain; timeout), H3-01(plain; timeout), H3-03(plain; timeout), H3-04(trap; timeout), H3-05(trap; timeout), H3-06(trap; timeout), H3-07(trap; timeout), H3-08(none; timeout), H3-09(none; timeout), H3-11(none; timeout)
* H3:cypher:h3.shortestpath.cypher: wrong on H3-04(trap), H3-05(trap), H3-06(trap), H3-07(trap)

