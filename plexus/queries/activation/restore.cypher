// name: activation/restore
// purpose: Undo a sweep for one fact: a 'dormant' fact gets its prior_status back and loses prior_status / dormant_at, so the graph is exactly as before the sweep.
// params: fact_id:str
// returns: id, was (the status before this call), status (the status after it). No row = no such fact. A fact that is not dormant is left untouched (was = status).
// mode: rw

// Only a dormant fact is changed. prior_status is always 'active' for facts a sweep moved; coalesce keeps a hand-made dormant fact usable.
MATCH (f:Fact {id: $fact_id})
WITH f, f.status AS was
FOREACH (_ IN CASE WHEN was = 'dormant' THEN [1] ELSE [] END |
  SET f.status = coalesce(f.prior_status, 'active')
  REMOVE f.prior_status, f.dormant_at)
RETURN f.id AS id, was, f.status AS status
