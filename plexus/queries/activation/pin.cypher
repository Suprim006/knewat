// name: activation/pin
// purpose: Pin or unpin a fact (D-012): a pinned fact is protected, so its activation is never taken as lower than neutral and a sweep never moves it.
// params: fact_id:str, pinned:bool
// returns: id, status, pinned (the value now stored). No row = no such fact (nothing written).
// mode: rw

// One fact, one property. Any status can be pinned (pinning a dormant fact does not restore it: use restore_fact).
MATCH (f:Fact {id: $fact_id})
SET f.pinned = $pinned
RETURN f.id AS id, f.status AS status, f.pinned AS pinned
