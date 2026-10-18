// name: activation/pin
// purpose: Pin or unpin a fact (D-012): a pinned fact is protected, so its activation is never taken as lower than neutral and a sweep never moves it. D-013: pinning also caches Fact.salience >= 0.95 (salience_at = now); unpinning drops the cached value so the next read recomputes it from the graph.
// params: fact_id:str, pinned:bool, now:int
// returns: id, status, pinned (the value now stored), salience (the cached value, null after an unpin). No row = no such fact (nothing written).
// mode: rw

// One fact, one statement. Any status can be pinned (pinning a dormant fact does not restore it: use restore_fact).
// The salience formula (knewat.activation.service.salience_of) gives a pinned fact >= 0.95 on its own; the cache mirrors that so the
// viewer and the sweep's protection see it without a recompute. FOREACH over a 0/1-element list is the 6.0.2-safe conditional write.
MATCH (f:Fact {id: $fact_id})
SET f.pinned = $pinned
FOREACH (_ IN CASE WHEN $pinned THEN [1] ELSE [] END |
  SET f.salience = CASE WHEN coalesce(f.salience, 0.0) < 0.95 THEN 0.95 ELSE f.salience END, f.salience_at = $now)
FOREACH (_ IN CASE WHEN $pinned THEN [] ELSE [1] END |
  REMOVE f.salience, f.salience_at)
RETURN f.id AS id, f.status AS status, f.pinned AS pinned, f.salience AS salience
