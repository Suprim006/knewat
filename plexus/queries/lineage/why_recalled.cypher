// name: lineage/why_recalled
// purpose: Explain a stored Recall: its header, and for every fact it RETURNED (rank, score) the fact's ABOUT entity, ASSERTED_BY agents, one-hop DERIVED_FROM origins and IN_SCOPE scope.
// params: recall_id:str, limit:int
// returns: one row per returned fact in rank order: recall_id, query, at, k, scope_id, agent_id, entities ([] when absent), separation (false when absent), step [{id,n,at}], fact_id, rank, score, sep (0 when absent), predicate, value, status, valid_from, valid_to, entity [{id,name}], asserted_by [agent ids], derived_from [{id,label}], scope [{id,name,kind}]. A recall that returned nothing gives one row with fact_id null; an unknown recall gives no rows.
// mode: ro
MATCH (r:Recall {id: $recall_id})
OPTIONAL MATCH (r)-[x:RETURNED]->(f:Fact)
WITH r, x, f ORDER BY x.rank ASC LIMIT $limit
RETURN r.id AS recall_id, r.query AS query, r.at AS at, r.k AS k, r.scope_id AS scope_id, r.agent_id AS agent_id,
       coalesce(r.entities, []) AS entities, coalesce(r.separation, false) AS separation,
       [(r)-[:IN_STEP]->(s:Step) | {id: s.id, n: s.n, at: s.at}] AS step,
       f.id AS fact_id, x.rank AS rank, x.score AS score, coalesce(x.sep, 0.0) AS sep,
       f.predicate AS predicate, f.value AS value, f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to,
       [(f)-[:ABOUT]->(e:Entity) | {id: e.id, name: e.name}] AS entity,
       [(f)-[:ASSERTED_BY]->(a:Agent) | a.id] AS asserted_by,
       [(f)-[:DERIVED_FROM]->(d) | {id: d.id, label: labels(d)[0]}] AS derived_from,
       [(f)-[:IN_SCOPE]->(sc:Scope) | {id: sc.id, name: sc.name, kind: sc.kind}] AS scope
