// name: engram/recall
// purpose: Hybrid recall in ONE read: vector (+ keyword) seeds over Fact.embedding, scope-inheritance + validity-window + status filter, 1-hop ABOUT-entity expansion to sibling facts (boosted, capped), nearest first, with provenance for the why-path.
// params: q:list[float], scope_id:str, over:int, k:int, t:int, statuses:list[str], boost:float, sibs:int, kw_ids:list[str]
// returns: fact_id, entity_id, entity_name, predicate, value, status, confidence, valid_from, valid_to, scope_id, score (cosine distance to the query, lower = nearer), rank (score after the sibling boost; what the order is by), via (seed fact id when reached by expansion, else null), raw (how many nodes the vector index returned before filtering; < over means the index is exhausted), derived_from [{id,label}], asserted_by [agent ids]
// mode: ro

// Scopes searched: the given scope plus everything it INHERITS (<=3 hops). Facts are valid at t when valid_from <= t < valid_to.
// Seeds: the top `over` nearest facts of the WHOLE graph plus the facts in kw_ids (full-text hits from engram/recall_keywords),
// then filtered. LIMITATION: FalkorDB's vector procedure has no pre-filter, so scope/status/validity are applied AFTER the
// index returns `over` nodes; nearer out-of-scope or superseded facts can crowd the target out. The Python wrapper therefore
// re-runs with a larger `over` (x4, up to 512) while fewer than k rows come back and `raw` == `over`.
// Expansion: the `sibs` nearest other facts on the seed's entity that pass the same filters; they are ranked by
// (own distance - boost), floor 0, but report their own distance as `score`. A fact reached both ways counts as a seed (via null)
// and keeps its best rank.
MATCH (:Scope {id: $scope_id})-[:INHERITS*0..3]->(a:Scope)
WITH collect(DISTINCT a.id) AS sids
CALL db.idx.vector.queryNodes('Fact', 'embedding', $over, vecf32($q)) YIELD node, score
WITH sids, collect({n: node, s: score}) AS vh
OPTIONAL MATCH (kx:Fact) WHERE kx.id IN $kw_ids
WITH sids, vh, collect({n: kx, s: vec.cosineDistance(kx.embedding, vecf32($q))}) AS kh
UNWIND vh + kh AS h
WITH sids, size(vh) AS raw, h WHERE h.n IS NOT NULL
WITH sids, raw, h.n AS f, min(h.s) AS score
WHERE f.status IN $statuses AND f.valid_from <= $t AND $t < f.valid_to
MATCH (f)-[:IN_SCOPE]->(fs:Scope)
WHERE fs.id IN sids
MATCH (f)-[:ABOUT]->(e:Entity)
WITH sids, raw, f, e, score
ORDER BY score ASC
LIMIT $k
OPTIONAL MATCH (e)<-[:ABOUT]-(g:Fact)-[:IN_SCOPE]->(gs:Scope)
  WHERE gs.id IN sids AND g.id <> f.id AND g.status IN $statuses AND g.valid_from <= $t AND $t < g.valid_to
WITH raw, f, e, score, g, CASE WHEN g IS NULL THEN 2.0 ELSE vec.cosineDistance(g.embedding, vecf32($q)) END AS gd
ORDER BY gd ASC
WITH raw, f, e, score, collect({g: g, d: gd})[0..$sibs] AS sibs
WITH raw, [{n: f, rank: score, dist: score, seed: 1, via: f.id}]
     + [s IN sibs WHERE s.g IS NOT NULL | {n: s.g, rank: CASE WHEN s.d - $boost < 0 THEN 0.0 ELSE s.d - $boost END, dist: s.d, seed: 0, via: f.id}] AS cands
UNWIND cands AS c
WITH raw, c.n AS n, min(c.rank) AS rank, min(c.dist) AS dist, max(c.seed) AS isseed, collect(CASE WHEN c.seed = 0 THEN c.via END) AS vias
ORDER BY rank ASC
LIMIT $k
MATCH (n)-[:ABOUT]->(en:Entity)
MATCH (n)-[:IN_SCOPE]->(ns:Scope)
RETURN n.id AS fact_id, en.id AS entity_id, en.name AS entity_name, n.predicate AS predicate, n.value AS value,
       n.status AS status, n.confidence AS confidence, n.valid_from AS valid_from, n.valid_to AS valid_to,
       ns.id AS scope_id, dist AS score, rank, CASE WHEN isseed = 1 THEN null ELSE head(vias) END AS via, raw,
       [(n)-[:DERIVED_FROM]->(d) | {id: d.id, label: labels(d)[0]}] AS derived_from,
       [(n)-[:ASSERTED_BY]->(ag:Agent) | ag.id] AS asserted_by
ORDER BY rank ASC
