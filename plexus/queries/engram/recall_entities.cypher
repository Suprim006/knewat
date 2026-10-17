// name: engram/recall_entities
// purpose: Pattern separation at recall (D-013 P1): the entities a recall query names (full-text on Entity.name, OR of the query words) with each one's fan = its current facts in the searched scopes; bounded to $limit entities.
// params: q:str (RediSearch syntax: words joined by a pipe = OR), scope_id:str, limit:int, statuses:list[str], t:int
// returns: entity_id, name, score (full-text relevance, higher = better), fan (facts ABOUT the entity with status in statuses, valid at t, in the scope or a scope it INHERITS <= 3 hops; 0 when none); best first, then id. No rows when the scope does not exist.
// mode: ro
// The Python wrapper (plexus.engram.service.Engram._resolve_entities) keeps only the entities whose every name word appears in the query
// (the OR query also returns entities that share one word, e.g. every "Acme Notes API Sxx" twin for "Acme Notes API S07 api_version";
// a twin must not get the entity lift). plexus.activation.rank turns the fan into the lift gamma * max(0, 1 - ln(fan) / S_max).
// Plan shape (tests/integration/test_p5_plans.py): full-text index scan on Entity, then the entity's ABOUT edges with the cheap
// property filters, then the scope test with the fact bound (an entity-first OPTIONAL MATCH + CASE, as in engram/recall; written as
// one pattern `(e)<-[:ABOUT]-(f)-[:IN_SCOPE]->(s) WHERE s.id IN sids` the 6.0.2 planner starts at the Scope). A WHERE on the second
// OPTIONAL MATCH would drop the entity's row on 6.0.2 when nothing matches, so the scope test yields null inside a CASE and count()
// skips it: an entity with no in-scope fact is still returned with fan 0 (it is a match, it just lifts nothing yet).
MATCH (:Scope {id: $scope_id})-[:INHERITS*0..3]->(a:Scope)
WITH collect(DISTINCT a.id) AS sids
CALL db.idx.fulltext.queryNodes('Entity', $q) YIELD node AS e, score
WITH sids, e, score
ORDER BY score DESC
LIMIT $limit
OPTIONAL MATCH (e)<-[:ABOUT]-(f:Fact)
  WHERE f.status IN $statuses AND f.valid_from <= $t AND $t < f.valid_to
WITH sids, e, score, f
OPTIONAL MATCH (f)-[:IN_SCOPE]->(fs:Scope)
  WHERE fs.id IN sids
WITH e, score, CASE WHEN fs IS NULL THEN null ELSE f END AS g
RETURN e.id AS entity_id, e.name AS name, score, count(g) AS fan
ORDER BY score DESC, e.id ASC
