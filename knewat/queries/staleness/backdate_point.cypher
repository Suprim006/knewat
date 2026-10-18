// name: staleness/backdate_point
// purpose: The read half of verify_fact(changed), run BEFORE the new value is asserted: the event time the old fact's window would end at, so a failing read leaves the graph untouched.
// params: old_id:str, now:int
// returns: change_at (the newest Change that SUSPECTED the old fact with at < now and at > the fact's last confirmation (verified_at), or -1 when there is none). Zero rows = no such fact.
// mode: ro
// staleness/backdate applies it only if old.valid_from < change_at < old.valid_to and the new fact is brand new. A Change at or before the last confirmation is skipped.
MATCH (old:Fact {id: $old_id})
OPTIONAL MATCH (ch:Change)-[:SUSPECTED]->(old)
WITH old, max(CASE WHEN ch.at < $now AND ch.at > coalesce(old.verified_at, 0) THEN ch.at END) AS cat
RETURN coalesce(cat, -1) AS change_at
