// name: engram/recall
// purpose: Hybrid recall in ONE read: vector (+ keyword) seeds over Fact.embedding, scope-inheritance + validity-window + status filter, 1-hop ABOUT-entity expansion to sibling facts (boosted, capped), nearest first, with provenance for the why-path.
// params: q:list[float], scope_id:str, over:int, k:int, t:int, statuses:list[str], boost:float, sibs:int, kw_ids:list[str], damp:bool, smax:float
// returns: fact_id, entity_id, entity_name, predicate, value, status, confidence, valid_from, valid_to, scope_id, score (cosine distance to the query, lower = nearer), rank (score after the sibling boost; what the order is by), via (seed fact id when reached by expansion, else null), raw (how many nodes the vector index returned before filtering; < over means the index is exhausted), derived_from [{id,label}], asserted_by [agent ids], surprise (0 when absent), verify_state ('verified' when absent), suspect_since (0 when absent), verify_after (9999999999999 = OPEN when absent), maybe_dup [ids of the facts this one is a possible duplicate of: (n)-[:DUPLICATES_MAYBE]->(o), P9-c]
// mode: ro

// P7 (D-012): the statuses list is a parameter: ['active'] by default, + 'dormant' with include_dormant, + 'superseded' and 'dormant' for as_of. The extra row fields are plain
// properties of the matched fact (read with coalesce, absent on facts written before P7); the activation re-ranking happens in Python on these rows (plexus.activation.rank).
// Scopes searched: the given scope plus everything it INHERITS (<=3 hops). Facts are valid at t when valid_from <= t < valid_to.
// Seeds: the top `over` nearest facts of the WHOLE graph plus the facts in kw_ids (full-text hits from engram/recall_keywords),
// then filtered. LIMITATION: FalkorDB's vector procedure has no pre-filter, so scope/status/validity are applied AFTER the
// index returns `over` nodes; nearer out-of-scope or superseded facts can crowd the target out. The Python wrapper therefore
// re-runs with a larger `over` (x4, up to 512) while fewer than k rows come back and `raw` == `over`.
// Expansion: the `sibs` nearest other facts on the seed's entity that pass the same filters; they are ranked by
// (own distance - boost), floor 0, but report their own distance as `score`. A fact reached both ways counts as a seed (via null)
// and keeps its best rank.
// Plan shape (P5 review Q1): the sibling expansion is ENTITY-first: (e)<-[:ABOUT]-(g0:Fact) with the cheap property filters, then
// the scope test with g0 already bound (separate OPTIONAL MATCH after a WITH). Written as one pattern
// `(e)<-[:ABOUT]-(g)-[:IN_SCOPE]->(gs:Scope) WHERE gs.id IN sids` the planner starts at the Scope and walks every fact IN_SCOPE of it for
// every seed, so recall latency grew with the facts in the scope instead of the entity's fan-out (tests/integration/test_p5_plans.py).
// Fan-damped expansion (D-013 P1, §2.3): with damp = true the sibling boost is scaled by max(0, 1 - ln(fan_e) / smax) where fan_e is the
// seed entity's number of active facts (ACT-R fan): completing the pattern around a small, specific entity stays strong, expansion from a
// hub entity (fan >= e^smax, 50 by default) is damped to nothing. damp = false (PLEXUS_RECALL_SEPARATION=off) is the pre-D-013 rank exactly.
// fan_e is bound by one pattern comprehension in its own WITH, before the collect (an aggregate next to a comprehension misbehaves on 6.0.2).
// The keyword seeds are looked up one id at a time (`{id: kid}` is an index seek); `kx.id IN $kw_ids` planned a scan of the whole Fact
// id index even for an empty list. The '' placeholder keeps the row alive when there are no keyword hits (no Fact has the id '').
MATCH (:Scope {id: $scope_id})-[:INHERITS*0..3]->(a:Scope)
WITH collect(DISTINCT a.id) AS sids
CALL db.idx.vector.queryNodes('Fact', 'embedding', $over, vecf32($q)) YIELD node, score
WITH sids, collect({n: node, s: score}) AS vh
UNWIND CASE WHEN size($kw_ids) = 0 THEN [''] ELSE $kw_ids END AS kid
OPTIONAL MATCH (kx:Fact {id: kid})
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
WITH sids, raw, f, e, score, size([(e)<-[:ABOUT]-(:Fact {status: 'active'}) | 1]) AS fan_e
WITH sids, raw, f, e, score,
     CASE WHEN NOT $damp THEN 1.0 WHEN fan_e < 1 THEN 1.0 WHEN log(fan_e) >= $smax THEN 0.0 ELSE 1.0 - log(fan_e) / $smax END AS damp
OPTIONAL MATCH (e)<-[:ABOUT]-(g0:Fact)
  WHERE g0.id <> f.id AND g0.status IN $statuses AND g0.valid_from <= $t AND $t < g0.valid_to
WITH sids, raw, f, e, score, damp, g0
OPTIONAL MATCH (g0)-[:IN_SCOPE]->(gs:Scope)
  WHERE gs.id IN sids
WITH raw, f, e, score, damp, CASE WHEN gs IS NULL THEN null ELSE g0 END AS g
WITH raw, f, e, score, damp, g, CASE WHEN g IS NULL THEN 2.0 ELSE vec.cosineDistance(g.embedding, vecf32($q)) END AS gd
ORDER BY gd ASC
WITH raw, f, e, score, damp, collect({g: g, d: gd})[0..$sibs] AS sibs
WITH raw, [{n: f, rank: score, dist: score, seed: 1, via: f.id}]
     + [s IN sibs WHERE s.g IS NOT NULL | {n: s.g, rank: CASE WHEN s.d - $boost * damp < 0 THEN 0.0 ELSE s.d - $boost * damp END, dist: s.d, seed: 0, via: f.id}] AS cands
UNWIND cands AS c
WITH raw, c.n AS n, min(c.rank) AS rank, min(c.dist) AS dist, max(c.seed) AS isseed, collect(CASE WHEN c.seed = 0 THEN c.via END) AS vias
ORDER BY rank ASC
LIMIT $k
MATCH (n)-[:ABOUT]->(en:Entity)
MATCH (n)-[:IN_SCOPE]->(ns:Scope)
RETURN n.id AS fact_id, en.id AS entity_id, en.name AS entity_name, n.predicate AS predicate, n.value AS value,
       n.status AS status, n.confidence AS confidence, n.valid_from AS valid_from, n.valid_to AS valid_to,
       ns.id AS scope_id, dist AS score, rank, CASE WHEN isseed = 1 THEN null ELSE head(vias) END AS via, raw,
       coalesce(n.surprise, 0.0) AS surprise, coalesce(n.verify_state, 'verified') AS verify_state,
       coalesce(n.suspect_since, 0) AS suspect_since, coalesce(n.verify_after, 9999999999999) AS verify_after,
       [(n)-[:DERIVED_FROM]->(d) | {id: d.id, label: labels(d)[0]}] AS derived_from,
       [(n)-[:ASSERTED_BY]->(ag:Agent) | ag.id] AS asserted_by,
       [(n)-[:DUPLICATES_MAYBE]->(mo:Fact) | mo.id] AS maybe_dup
ORDER BY rank ASC
