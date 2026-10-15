// name: staleness/suspect_ids
// purpose: Ids of the active facts that are suspect at time $now by the contract rule: verify_state = 'suspect' OR verify_after <= now.
// params: now:int, cap:int
// returns: id (distinct, at most 2 x cap rows before de-duplication)
// mode: ro
// Two index-backed branches instead of one OR: Fact(verify_state) equality, and Fact(verify_after) range. Facts written before P7 have neither property and are never returned (absent = verified, no review date).
MATCH (f:Fact {verify_state: 'suspect', status: 'active'})
RETURN f.id AS id LIMIT $cap
UNION
MATCH (f:Fact) WHERE f.verify_after <= $now AND f.status = 'active'
RETURN f.id AS id LIMIT $cap
