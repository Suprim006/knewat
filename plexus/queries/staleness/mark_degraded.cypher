// name: staleness/mark_degraded
// purpose: Record that verify_fact(changed) superseded the old fact but could not finish: Fact.verify_degraded = true. Calling verify_fact again with the same new value finishes the job (staleness/backdate clears the flag).
// params: fact_id:str
// returns: fact_id. Zero rows = no such fact.
// mode: rw
MATCH (f:Fact {id: $fact_id})
SET f.verify_degraded = true
RETURN f.id AS fact_id
