// name: lineage/why_edges
// purpose: The provenance subgraph behind a Decision or a Fact as a flat edge list, built from independent UNION branches (no node properties; lineage/node_info adds those).
// params: id:str, limit:int
// returns: s, sl, rel, t, tl, prio. One row per distinct edge: stored direction s -[rel]-> t with the node ids and labels; prio orders the rows for truncation (1 = closest to the root).
// mode: ro
// Root = a Decision (its BASED_ON facts become the base facts) or a Fact (the base fact is the fact itself); an unknown id returns no rows.
// Decision edges: DECIDED, FOR (Task), BASED_ON, (Step)-[:WROTE]->, and the writing Step's agent.
// Per base fact: ASSERTED_BY, ABOUT, IN_SCOPE (the DERIVED_FROM ancestry, with the asserting agent of derived facts and the Session/agent behind an Episode,
// comes from lineage/why_derived_level, which Lineage.why runs level by level over DISTINCT facts up to `depth` hops: P9-b),
// SUPERSEDES / CONTRADICTS / DUPLICATES neighbours (both directions), and the Step(s) that WROTE it with their agent.
// P7-int: the Changes that SUSPECTED a base fact (Change -> Fact) and the agents that VERIFIED_BY it (Fact -> Agent), so "why is this decision at risk" is this one query.
// Every branch is capped by $limit rows, and a base fact's neighbourhood is fixed, so the result is bounded.
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
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (ch:Change)-[:SUSPECTED]->(f)
RETURN ch.id AS s, 'Change' AS sl, 'SUSPECTED' AS rel, f.id AS t, 'Fact' AS tl, 2 AS prio LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:VERIFIED_BY]->(a:Agent)
RETURN DISTINCT f.id AS s, 'Fact' AS sl, 'VERIFIED_BY' AS rel, a.id AS t, 'Agent' AS tl, 2 AS prio LIMIT $limit
