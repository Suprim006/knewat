// name: engram/recall
// purpose: Hybrid recall in ONE read: vector seeds over Fact.embedding, scope-inheritance + validity-window + status filter, 1-hop ABOUT-entity expansion to sibling facts (boosted), nearest first, with provenance for the why-path.
// params: q:list[float], scope_id:str, over:int, k:int, t:int, statuses:list[str], boost:float
// returns: fact_id, entity_id, entity_name, predicate, value, status, confidence, valid_from, valid_to, scope_id, score (cosine distance to the query, lower = nearer), via (seed fact id when reached by expansion, else null), derived_from [{id,label}], asserted_by [agent ids]
// mode: ro

// Scopes searched: the given scope plus everything it INHERITS (<=3 hops). Facts are valid at t when valid_from <= t < valid_to.
// Seeds: top `over` (= k*4) nearest facts, filtered. Expansion: other facts on the seed's entity that pass the same filters;
// they are ranked by (own distance - boost), floor 0, but report their own distance as `score`. Duplicates keep the best rank.
MATCH (:Scope {id: $scope_id})-[:INHERITS*0..3]->(a:Scope)
WITH collect(DISTINCT a.id) AS sids
CALL db.idx.vector.queryNodes('Fact', 'embedding', $over, vecf32($q)) YIELD node, score
WITH sids, node AS f, score
WHERE f.status IN $statuses AND f.valid_from <= $t AND $t < f.valid_to
MATCH (f)-[:IN_SCOPE]->(fs:Scope)
WHERE fs.id IN sids
MATCH (f)-[:ABOUT]->(e:Entity)
WITH sids, f, e, score
ORDER BY score ASC
LIMIT $k
OPTIONAL MATCH (e)<-[:ABOUT]-(g:Fact)-[:IN_SCOPE]->(gs:Scope)
  WHERE gs.id IN sids AND g.id <> f.id AND g.status IN $statuses AND g.valid_from <= $t AND $t < g.valid_to
WITH f, e, score, collect({g: g, d: vec.cosineDistance(g.embedding, vecf32($q))}) AS sibs
WITH [{n: f, rank: score, dist: score, via: null}]
     + [s IN sibs WHERE s.g IS NOT NULL | {n: s.g, rank: CASE WHEN s.d - $boost < 0 THEN 0.0 ELSE s.d - $boost END, dist: s.d, via: f.id}] AS cands
UNWIND cands AS c
WITH c ORDER BY c.rank ASC
WITH c.n AS n, collect(c)[0] AS best
ORDER BY best.rank ASC
LIMIT $k
MATCH (n)-[:ABOUT]->(en:Entity)
MATCH (n)-[:IN_SCOPE]->(ns:Scope)
RETURN n.id AS fact_id, en.id AS entity_id, en.name AS entity_name, n.predicate AS predicate, n.value AS value,
       n.status AS status, n.confidence AS confidence, n.valid_from AS valid_from, n.valid_to AS valid_to,
       ns.id AS scope_id, best.dist AS score, best.via AS via,
       [(n)-[:DERIVED_FROM]->(d) | {id: d.id, label: labels(d)[0]}] AS derived_from,
       [(n)-[:ASSERTED_BY]->(ag:Agent) | ag.id] AS asserted_by
ORDER BY best.rank ASC
