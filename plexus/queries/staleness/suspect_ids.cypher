// name: staleness/suspect_ids
// purpose: Ids of the active facts that are suspect at time $now by the contract rule (verify_state = 'suspect' OR verify_after <= now), plus every fact with an unfinished verification (verify_degraded = true), whatever its status.
// params: now:int, cap:int
// returns: id (distinct, at most 3 x cap rows before de-duplication)
// mode: ro
// Three index-backed branches instead of one OR: Fact(verify_state) equality, Fact(verify_after) range, Fact(verify_degraded) equality (P12-F3: an interrupted verify_fact(changed); the old fact may already be 'superseded', so that branch has no status filter). Facts written before P7 have neither property and are never returned (absent = verified, no review date).
MATCH (f:Fact {verify_state: 'suspect', status: 'active'})
RETURN f.id AS id LIMIT $cap
UNION
MATCH (f:Fact) WHERE f.verify_after <= $now AND f.status = 'active'
RETURN f.id AS id LIMIT $cap
UNION
MATCH (f:Fact {verify_degraded: true})
RETURN f.id AS id LIMIT $cap
