// name: engram/recall_hop_facts
// purpose: The current facts of a set of entities reached over RELATES, nearest to the query first within each entity, in the row shape of engram/recall (for recall(hops)).
// params: entity_ids:list[str], scope_id:str, all:bool, t:int, statuses:list[str], per_entity:int, q:list[float]
// returns: the engram/recall columns: fact_id, entity_id, entity_name, predicate, value, status, confidence, valid_from, valid_to, scope_id, score (own cosine distance to the query), rank (= score; the caller adds the hop penalty), via (null), raw (0), surprise, verify_state, suspect_since, verify_after, derived_from, asserted_by
// mode: ro
// Same filters as engram/recall: facts in the scope or a scope it INHERITS (<= 3 hops; every scope with $all), status in `statuses`, valid at t (valid_from <= t < valid_to). At most `per_entity` facts per entity.
// Plan shape: ENTITY-first, like the sibling expansion of engram/recall (P5 review Q1): (e)<-[:ABOUT]-(g0) with the cheap property filters, then the scope test with the fact's own scope bound
// as a pattern PREDICATE (`WHERE $all OR (:Scope {id: $scope_id})-[:INHERITS*0..3]->(gs)`: one boolean per fact). Audit C2: a post-DISTINCT `MATCH (:Scope)-[:INHERITS*0..3]->(gs)`
// emitted one row per PATH, so on a diamond scope graph (team -> org directly and through proj) the org fact came back twice and filled two per_entity slots.
// P12: `$all` (recall scope 'all') keeps the facts of every scope; without it a fact outside the scope's INHERITS closure is dropped exactly as the MATCH did.
// (The `WITH collect(sids) UNWIND $ids MATCH` form returned no rows on 6.0.2.)
UNWIND $entity_ids AS eid
MATCH (e:Entity {id: eid})
WITH e
MATCH (e)<-[:ABOUT]-(g0:Fact)
WHERE g0.status IN $statuses AND g0.valid_from <= $t AND $t < g0.valid_to
WITH e, g0
MATCH (g0)-[:IN_SCOPE]->(gs:Scope)
WITH e, g0 AS g, gs
WHERE $all OR (:Scope {id: $scope_id})-[:INHERITS*0..3]->(gs)
WITH e, g, vec.cosineDistance(g.embedding, vecf32($q)) AS gd
ORDER BY gd ASC
WITH e, collect({g: g, d: gd})[0..$per_entity] AS top
UNWIND top AS x
WITH e, x.g AS n, x.d AS dist
MATCH (n)-[:IN_SCOPE]->(ns:Scope)
RETURN n.id AS fact_id, e.id AS entity_id, e.name AS entity_name, n.predicate AS predicate, n.value AS value,
       n.status AS status, n.confidence AS confidence, n.valid_from AS valid_from, n.valid_to AS valid_to,
       ns.id AS scope_id, dist AS score, dist AS rank, null AS via, 0 AS raw,
       coalesce(n.surprise, 0.0) AS surprise, coalesce(n.verify_state, 'verified') AS verify_state,
       coalesce(n.suspect_since, 0) AS suspect_since, coalesce(n.verify_after, 9999999999999) AS verify_after,
       [(n)-[:DERIVED_FROM]->(d) | {id: d.id, label: labels(d)[0]}] AS derived_from,
       [(n)-[:ASSERTED_BY]->(ag:Agent) | ag.id] AS asserted_by
ORDER BY dist ASC
