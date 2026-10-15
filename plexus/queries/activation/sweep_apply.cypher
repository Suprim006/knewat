// name: activation/sweep_apply
// purpose: ONE bounded statement: move the given ACTIVE facts to status 'dormant' (reversible, nothing is deleted), re-checking protection inside the statement.
// params: fact_ids:list[str], now:int
// returns: id of each fact that was moved; a fact that is not active, or became protected since it was listed, is skipped silently
// mode: rw

// Bounded by UNWIND: callers pass at most 200 ids. prior_status and dormant_at are kept so activation/restore can put the fact back exactly.
// Protection re-check (the same rules as the activation lookup; the activation THRESHOLD itself is checked by the caller): skipped when the fact is pinned, suspect
// (verify_state or a passed verify_after), CARRIED by any Handoff, the start of a SUPERSEDES edge, at either end of a CONTRADICTS edge, derived (DERIVED_FROM 1..3)
// from a Source whose trust is 'high', or BASED_ON by a Decision whose flagged is not true.
// FalkorDB 6.0.2 gotchas (each produced a fact that was swept although protected; tests/activation/test_sweep_restore.py pins them): a chain of aggregating
// OPTIONAL MATCHes (one count per rule) gives wrong counts for the later ones, and a variable-length OPTIONAL MATCH after another aggregation matches nothing.
// So every rule that is a plain existence test is a pattern predicate in one WHERE, and only the flagged-decision rule (it needs a property test on the Decision)
// uses one OPTIONAL MATCH + count, last.
UNWIND $fact_ids AS fid
MATCH (f:Fact {id: fid, status: 'active'})
WITH f
WHERE coalesce(f.pinned, false) = false
  AND coalesce(f.verify_state, 'verified') <> 'suspect'
  AND coalesce(f.verify_after, 9999999999999) > $now
  AND NOT (:Handoff)-[:CARRIES]->(f)
  AND NOT (f)-[:SUPERSEDES]->(:Fact)
  AND NOT (f)-[:CONTRADICTS]-(:Fact)
  AND NOT (f)-[:DERIVED_FROM*1..3]->(:Source {trust: 'high'})
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(f) WHERE coalesce(d.flagged, false) <> true
WITH f, count(d) AS n_decisions WHERE n_decisions = 0
SET f.prior_status = f.status, f.status = 'dormant', f.dormant_at = $now
RETURN f.id AS id
