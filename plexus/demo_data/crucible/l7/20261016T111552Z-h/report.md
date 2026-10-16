# Crucible L7 family H: expressiveness and traversal (20261016T111552Z-h)

SQLite = embedded (in-process); FalkorDB = server (Docker port-forward). Lines = non-blank non-comment lines of the statement file; app lines = Python BFS lines (for `+app-bfs`).

## scale small: {'agents': 50, 'sources': 100, 'facts': 2061, 'fact_parents': 2900, 'fact_source': 769, 'steps': 1220, 'reads': 3007, 'decisions': 100, 'based_on': 206, 'handoffs': 90, 'carries': 114}

| question | arm | lines | app lines | statements (max) | strict | timeouts | errors | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| H1a | cypher h1a.cypher | 5 | 0 | 1 | 1/1 | 0 | 0 | 5.301 | 6.533 |
| H1a | sql h1a.sql | 12 | 0 | 1 | 1/1 | 0 | 0 | 5.874 | 7.865 |
| H1b | cypher h1b.cypher | 7 | 0 | 1 | 1/1 | 0 | 0 | 2.779 | 3.068 |
| H1b | sql h1b.sql | 20 | 0 | 1 | 1/1 | 0 | 0 | 0.118 | 0.723 |
| H1c | cypher h1c.cypher | 13 | 0 | 1 | 1/1 | 0 | 0 | 306.739 | 328.621 |
| H1c | sql h1c.sql | 20 | 0 | 1 | 1/1 | 0 | 0 | 35.428 | 35.688 |
| H2 | cypher h2.cypher | 6 | 0 | 1 | 24/24 | 0 | 0 | 8.239 | 15.954 |
| H2 | sql h2.sql | 14 | 0 | 1 | 24/24 | 0 | 0 | 0.089 | 0.41 |
| H1c | cypher h1c.natural.cypher | 7 | 0 | 0 | 0/1 | 0 | 1 | 562.885 | 562.885 |
| H4 | cypher h4.naive.cypher | 3 | 0 | 1 | 1/1 | 0 | 0 | 2276.827 | 2377.646 |
| H4 | cypher h4.distinct.cypher | 7 | 0 | 1 | 1/1 | 0 | 0 | 8.364 | 9.097 |
| H4 | cypher h4.bfs.cypher | 8 | 0 | 1 | 1/1 | 0 | 0 | 90.578 | 104.784 |
| H4 | sql h4.sql | 8 | 0 | 1 | 1/1 | 0 | 0 | 7.087 | 8.26 |
| H3 | cypher h3.varlen.cypher | 4 | 0 | 1 | 12/12 | 0 | 0 | 2.581 | 3.985 |
| H3 | cypher h3.varlen.cypher+unbounded | 4 | 0 | 1 | 12/12 | 0 | 0 | 6.529 | 13.422 |
| H3 | cypher h3.shortestpath.cypher | 4 | 0 | 1 | 8/12 | 0 | 0 | 1.817 | 2.484 |
| H3 | sql h3.path_cte.sql | 9 | 0 | 1 | 12/12 | 0 | 0 | 0.095 | 0.391 |
| H3 | sql h3.path_cte.sql+unbounded | 9 | 0 | 1 | 12/12 | 0 | 0 | 0.141 | 0.358 |
| H3 | sql h3.depth_cte.sql | 8 | 0 | 1 | 12/12 | 0 | 0 | 0.093 | 0.198 |
| H3 | cypher h3.bfs_level.cypher+app-bfs | 3 | 18 | 11 | 12/12 | 0 | 0 | 7.92 | 22.118 |
| H3 | sql h3.bfs_level.sql+app-bfs | 3 | 18 | 11 | 12/12 | 0 | 0 | 0.105 | 0.298 |

* H1c:cypher:h1c.natural.cypher: wrong on H1c(; ResponseError: Query's mem consumption exceeded capacity)
* H3:cypher:h3.shortestpath.cypher: wrong on H3-04(trap), H3-05(trap), H3-06(trap), H3-07(trap)

## scale large: {'agents': 200, 'sources': 1000, 'facts': 50061, 'fact_parents': 68068, 'fact_source': 18675, 'steps': 30500, 'reads': 75510, 'decisions': 2500, 'based_on': 4970, 'handoffs': 1650, 'carries': 2398}

| question | arm | lines | app lines | statements (max) | strict | timeouts | errors | p50 ms | p99 ms |
|---|---|---|---|---|---|---|---|---|---|
| H1a | cypher h1a.cypher | 5 | 0 | 1 | 1/1 | 0 | 0 | 60.219 | 62.325 |
| H1a | sql h1a.sql | 12 | 0 | 1 | 1/1 | 0 | 0 | 355.654 | 419.655 |
| H1b | cypher h1b.cypher | 7 | 0 | 1 | 1/1 | 0 | 0 | 25.591 | 27.021 |
| H1b | sql h1b.sql | 20 | 0 | 1 | 1/1 | 0 | 0 | 5.098 | 6.609 |
| H1c | cypher h1c.cypher | 13 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H1c | sql h1c.sql | 20 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H2 | cypher h2.cypher | 6 | 0 | 1 | 24/24 | 0 | 0 | 575.371 | 863.024 |
| H2 | sql h2.sql | 14 | 0 | 1 | 24/24 | 0 | 0 | 0.64 | 4.213 |
| H1c | cypher h1c.natural.cypher | 7 | 0 | 0 | 0/1 | 0 | 1 | 604.509 | 604.509 |
| H4 | cypher h4.naive.cypher | 3 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H4 | cypher h4.distinct.cypher | 7 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H4 | cypher h4.bfs.cypher | 8 | 0 | 0 | 0/1 | 1 | 0 | 10000.0 | 10000.0 |
| H4 | sql h4.sql | 8 | 0 | 1 | 1/1 | 0 | 0 | 7385.52 | 7467.202 |
| H3 | cypher h3.varlen.cypher | 4 | 0 | 1 | 12/12 | 0 | 0 | 2.672 | 3.72 |
| H3 | cypher h3.varlen.cypher+unbounded | 4 | 0 | 1 | 6/12 | 6 | 0 | 8441.378 | 10000.0 |
| H3 | cypher h3.shortestpath.cypher | 4 | 0 | 1 | 8/12 | 0 | 0 | 1.871 | 2.719 |
| H3 | sql h3.path_cte.sql | 9 | 0 | 1 | 12/12 | 0 | 0 | 0.11 | 0.648 |
| H3 | sql h3.path_cte.sql+unbounded | 9 | 0 | 1 | 12/12 | 0 | 0 | 0.291 | 1.333 |
| H3 | sql h3.depth_cte.sql | 8 | 0 | 1 | 12/12 | 0 | 0 | 0.109 | 0.606 |
| H3 | cypher h3.bfs_level.cypher+app-bfs | 3 | 18 | 25 | 12/12 | 0 | 0 | 9.75 | 54.423 |
| H3 | sql h3.bfs_level.sql+app-bfs | 3 | 18 | 25 | 12/12 | 0 | 0 | 0.143 | 1.205 |

* H1c:cypher:h1c.cypher: wrong on H1c(; timeout)
* H1c:sql:h1c.sql: wrong on H1c(; timeout)
* H1c:cypher:h1c.natural.cypher: wrong on H1c(; ResponseError: Query's mem consumption exceeded capacity)
* H4:cypher:h4.naive.cypher: wrong on H4(; timeout)
* H4:cypher:h4.distinct.cypher: wrong on H4(; timeout)
* H4:cypher:h4.bfs.cypher: wrong on H4(; timeout)
* H3:cypher:h3.varlen.cypher+unbounded: wrong on H3-00(plain; timeout), H3-04(trap; timeout), H3-05(trap; timeout), H3-07(trap; timeout), H3-09(none; timeout), H3-11(none; timeout)
* H3:cypher:h3.shortestpath.cypher: wrong on H3-04(trap), H3-05(trap), H3-06(trap), H3-07(trap)

