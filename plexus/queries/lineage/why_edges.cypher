// name: lineage/why_edges
// purpose: The provenance subgraph behind a Decision or a Fact as a flat edge list, built from independent UNION branches (no node properties; lineage/node_info adds those).
// params: id:str, limit:int
// returns: s, sl, rel, t, tl, prio. One row per distinct edge: stored direction s -[rel]-> t with the node ids and labels; prio orders the rows for truncation (1 = closest to the root).
// mode: ro
// Root = a Decision (its BASED_ON facts become the base facts) or a Fact (the base fact is the fact itself); an unknown id returns no rows.
// Decision edges: DECIDED, FOR (Task), BASED_ON, (Step)-[:WROTE]->, and the writing Step's agent.
// Per base fact: ASSERTED_BY, ABOUT, IN_SCOPE, DERIVED_FROM*1..3 (Episode | Source | Fact; with the asserting agent of derived facts and the Session/agent behind an Episode),
// SUPERSEDES / CONTRADICTS / DUPLICATES neighbours (both directions), and the Step(s) that WROTE it with their agent.
// Every branch is capped by $limit rows, and a base fact's neighbourhood is bounded by the fixed hop limits above, so the result is bounded.
MATCH (a:Agent)-[:DECIDED]->(d:Decision {id: $id})
RETURN a.id AS s, 'Agent' AS sl, 'DECIDED' AS rel, d.id AS t, 'Decision' AS tl, 1 AS prio LIMIT $limit
UNION
MATCH (d:Decision {id: $id})-[:FOR]->(k:Task)
RETURN d.id AS s, 'Decision' AS sl, 'FOR' AS rel, k.id AS t, 'Task' AS tl, 1 AS prio LIMIT $limit
UNION
MATCH (d:Decision {id: $id})-[:BASED_ON]->(f:Fact)
RETURN d.id AS s, 'Decision' AS sl, 'BASED_ON' AS rel, f.id AS t, 'Fact' AS tl, 1 AS prio LIMIT $limit
UNION
MATCH (st:Step)-[:WROTE]->(d:Decision {id: $id})
RETURN st.id AS s, 'Step' AS sl, 'WROTE' AS rel, d.id AS t, 'Decision' AS tl, 1 AS prio LIMIT $limit
UNION
MATCH (st:Step)-[:WROTE]->(:Decision {id: $id})
MATCH (st)-[:BY]->(a:Agent)
RETURN st.id AS s, 'Step' AS sl, 'BY' AS rel, a.id AS t, 'Agent' AS tl, 1 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:ASSERTED_BY]->(a:Agent)
RETURN f.id AS s, 'Fact' AS sl, 'ASSERTED_BY' AS rel, a.id AS t, 'Agent' AS tl, 2 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:ABOUT]->(e:Entity)
RETURN f.id AS s, 'Fact' AS sl, 'ABOUT' AS rel, e.id AS t, 'Entity' AS tl, 5 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:IN_SCOPE]->(sc:Scope)
RETURN f.id AS s, 'Fact' AS sl, 'IN_SCOPE' AS rel, sc.id AS t, 'Scope' AS tl, 6 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH p = (f)-[:DERIVED_FROM*1..3]->(x)
UNWIND relationships(p) AS r
RETURN DISTINCT startNode(r).id AS s, labels(startNode(r))[0] AS sl, 'DERIVED_FROM' AS rel,
       endNode(r).id AS t, labels(endNode(r))[0] AS tl, 3 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:DERIVED_FROM*1..3]->(g:Fact)-[:ASSERTED_BY]->(a:Agent)
RETURN DISTINCT g.id AS s, 'Fact' AS sl, 'ASSERTED_BY' AS rel, a.id AS t, 'Agent' AS tl, 4 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:DERIVED_FROM*1..3]->(e:Episode)<-[:HAS_EPISODE]-(se:Session)
RETURN DISTINCT se.id AS s, 'Session' AS sl, 'HAS_EPISODE' AS rel, e.id AS t, 'Episode' AS tl, 4 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:DERIVED_FROM*1..3]->(:Episode)<-[:HAS_EPISODE]-(se:Session)<-[:HAD]-(a:Agent)
RETURN DISTINCT a.id AS s, 'Agent' AS sl, 'HAD' AS rel, se.id AS t, 'Session' AS tl, 4 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[r:SUPERSEDES|CONTRADICTS|DUPLICATES]->(o:Fact)
RETURN f.id AS s, 'Fact' AS sl, type(r) AS rel, o.id AS t, 'Fact' AS tl, 3 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (o:Fact)-[r:SUPERSEDES|CONTRADICTS|DUPLICATES]->(f)
RETURN o.id AS s, 'Fact' AS sl, type(r) AS rel, f.id AS t, 'Fact' AS tl, 3 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (st:Step)-[:WROTE]->(f)
RETURN st.id AS s, 'Step' AS sl, 'WROTE' AS rel, f.id AS t, 'Fact' AS tl, 2 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (st:Step)-[:WROTE]->(f)
MATCH (st)-[:BY]->(a:Agent)
RETURN st.id AS s, 'Step' AS sl, 'BY' AS rel, a.id AS t, 'Agent' AS tl, 2 AS prio LIMIT $limit
