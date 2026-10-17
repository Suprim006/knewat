// name: engram/recall_predicates
// purpose: Pattern separation at recall, second cue (CROSS_CHECK §3.2): the fan of each predicate a recall query names = its current facts in the searched scopes; one index seek per predicate.
// params: predicates:list[str] (normalised Fact.predicate values; the Python wrapper passes the candidate predicates whose every word is in the query; at most 10), scope_id:str, statuses:list[str], t:int
// returns: predicate, fan (facts with that predicate, status in statuses, valid at t, in the scope or a scope it INHERITS <= 3 hops; 0 when none); one row per input predicate, in input order. No rows when the scope does not exist.
// mode: ro
// The mirror of engram/recall_entities for the predicate cue: plexus.engram.service.Engram._resolve_predicates keeps the candidate
// predicates whose every word appears in the query (the same rule as the named-entity rule), and this read counts each one's fan;
// plexus.activation.rank turns it into the cue w_predicate * max(0, S - ln fan).
// Plan shape (tests/integration/test_p5_plans.py): a range-index seek on Fact.predicate per input value (`{predicate: p}`; `IN $list`
// would scan the whole index), then the cheap property filters, then the scope test with the fact bound (OPTIONAL MATCH + CASE, as in
// engram/recall_entities: a WHERE on the second OPTIONAL MATCH would drop the predicate's row on 6.0.2 when nothing matches). count()
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
