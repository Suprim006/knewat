// name: crucible/l5_real_facts
// purpose: L5 forgetting harness read: the active facts of the played history with their subject, scope and whether an unflagged Decision rests on them (the "critical" class).
// params: limit:int
// returns: id, subject (the ABOUT entity), predicate, value, scope_id, created_at, decision_flags (one boolean per BASED_ON Decision: its flagged state)
// mode: ro
// Benchmark harness only. Run before the noise is added, so every row is a real fact. One row per active fact, bounded by limit.
MATCH (f:Fact {status: 'active'})-[:ABOUT]->(e:Entity)
MATCH (f)-[:IN_SCOPE]->(sc:Scope)
RETURN f.id AS id, e.name AS subject, f.predicate AS predicate, f.value AS value, sc.id AS scope_id, f.created_at AS created_at,
       [(d:Decision)-[:BASED_ON]->(f) | coalesce(d.flagged, false)] AS decision_flags
ORDER BY f.created_at ASC, f.id ASC
LIMIT $limit
