// name: activation/restore
// purpose: Undo a sweep for one fact: a 'dormant' fact gets its prior_status back and loses prior_status / dormant_at, so the graph is exactly as before the sweep.
// params: fact_id:str
// returns: id, was (the status before this call), status (the status after it). No row = no such fact. A fact that is not dormant is left untouched (was = status); a dormant fact derived from a forgotten / quarantined fact is left dormant (status = was).
// mode: rw

// Only a dormant fact is changed. prior_status is always 'active' for facts a sweep moved; coalesce keeps a hand-made dormant fact usable.
// P7-int: a dormant fact derived (DERIVED_FROM*1..5) from a fact that is forgotten or quarantined stays dormant, so a restore cannot revive what a
// forget_source / quarantine cascade should have taken (those cascades now include dormant facts; this guards data from before that rule).
MATCH (f:Fact {id: $fact_id})
WITH f, f.status AS was,
     any(s IN [(f)-[:DERIVED_FROM*1..5]->(p:Fact) | p.status] WHERE s IN ['forgotten', 'quarantined']) AS tainted
FOREACH (_ IN CASE WHEN was = 'dormant' AND NOT tainted THEN [1] ELSE [] END |
  SET f.status = coalesce(f.prior_status, 'active')
  REMOVE f.prior_status, f.dormant_at)
RETURN f.id AS id, was, f.status AS status
