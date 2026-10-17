// name: engram/recall_predicates
// purpose: Pattern separation at recall, second cue (CROSS_CHECK §3.2): the fan of each predicate a recall query names = its current facts in the searched scopes; one index seek per predicate.
// params: predicates:list[str] (normalised Fact.predicate values; the Python wrapper passes the candidate predicates whose every word is in the query; at most 10), scope_id:str, statuses:list[str], t:int
// returns: predicate, fan (facts with that predicate, status in statuses, valid at t, in the scope or a scope it INHERITS <= 3 hops; 0 when none); one row per DISTINCT input predicate, in no particular order (the caller builds a dict). A scope that does not exist gives every predicate with fan 0, not zero rows (the scope list is a key-less collect).
// mode: ro
// The mirror of engram/recall_entities for the predicate cue: plexus.engram.service.Engram._resolve_predicates keeps the candidate
// predicates whose every word appears in the query (the same rule as the named-entity rule), and this read counts each one's fan;
// plexus.activation.rank turns it into the cue w_predicate * max(0, S - ln fan).
// Plan shape (tests/integration/test_p5_plans.py, test_audit_recall_predicates_plan.py): a range-index seek on Fact per input value
// (`{predicate: p}`; `IN $list` would scan the whole index). On 6.0.2 the seek applies the indexed `status` and `valid_to` filters
// together with `predicate`, so the superseded history and the expired facts of that predicate are NOT read (measured, audit B2:
// 2,000 superseded + 1,500 expired + 200 current in scope + 500 current elsewhere -> 700 index records, 1.4 ms). What it does read is
// every CURRENT fact with that predicate in EVERY scope, then one IN_SCOPE hop per fact for the scope test (OPTIONAL MATCH + CASE,
// as in engram/recall_entities; the CASE is kept as a guard against the OPTIONAL-MATCH row-drop trap, which did not reproduce here).
// That cross-scope part is the cost of a common predicate in a tenant with many scopes: the scope is an edge, not an indexed Fact
// property, so no single-property index can absorb it (D-013 amendment 2). Bounded by RECALL_PREDICATES (10) per recall. count()
// skips the nulls, so a predicate with no in-scope fact still returns one row with fan 0.
MATCH (:Scope {id: $scope_id})-[:INHERITS*0..3]->(a:Scope)
WITH collect(DISTINCT a.id) AS sids
UNWIND $predicates AS p
OPTIONAL MATCH (f:Fact {predicate: p})
  WHERE f.status IN $statuses AND f.valid_from <= $t AND $t < f.valid_to
WITH sids, p, f
OPTIONAL MATCH (f)-[:IN_SCOPE]->(fs:Scope)
  WHERE fs.id IN sids
WITH p, CASE WHEN fs IS NULL THEN null ELSE f END AS g
RETURN p AS predicate, count(g) AS fan
