// name: engram/confirm_duplicate
// purpose: Merge a soft duplicate: the NEW fact becomes a duplicate of the OLD one. Reversible: nothing is deleted; engram/split_duplicate undoes it.
// params: new_id:str, old_id:str, open_to:int, now:int
// returns: new_id, old_id, reopened (true when the old fact had been closed by the new one and is current again), moved (agent ids that now also assert the old fact); no row when the link is missing or the facts are not in a mergeable state (the caller reads engram/duplicate_pair to say why)
// mode: rw

// Effects, in one statement:
//   * every agent that asserted NEW now also asserts OLD: MERGE (old)-[:ASSERTED_BY {at, text: <new wording>, via: new.id}]->agent. `via` marks the
//     edges this merge created (an agent that already asserted OLD keeps its edge unchanged), so split_duplicate can remove exactly those.
//   * NEW gets a zero-width window (valid_to = valid_from, status 'superseded'): as_of / recall never return it, and the row stays in the history.
//   * (new)-[:DUPLICATES {at, reopened}]->(old) records the decision; the soft link is consumed.
//   * if NEW had superseded OLD (same agent re-worded its value), OLD is current again: valid_to = open, status 'active', the SUPERSEDES edge is removed.
// Guards (race-tolerant: a lost race returns no row, nothing is written): the soft link exists, NEW is current, and OLD is current or reopenable.
MATCH (n:Fact {id: $new_id})-[l:DUPLICATES_MAYBE]->(o:Fact {id: $old_id})
WHERE n.valid_to = $open_to AND n.status IN ['active', 'dormant']
OPTIONAL MATCH (n)-[sup:SUPERSEDES]->(o)
WITH n, l, o, sup, (sup IS NOT NULL AND o.status = 'superseded' AND o.valid_to = n.valid_from) AS reopen
WHERE reopen OR (o.valid_to = $open_to AND o.status IN ['active', 'dormant'])
OPTIONAL MATCH (n)-[:ASSERTED_BY]->(ag:Agent)
OPTIONAL MATCH (o)-[have:ASSERTED_BY]->(ag)
WITH n, l, o, sup, reopen, ag, have
WITH n, l, o, sup, reopen, collect(CASE WHEN ag IS NOT NULL AND have IS NULL THEN ag END) AS fresh
FOREACH (g IN fresh | CREATE (o)-[:ASSERTED_BY {at: $now, text: n.value, via: n.id}]->(g))
FOREACH (r IN CASE WHEN reopen THEN [o] ELSE [] END | SET r.valid_to = $open_to, r.status = 'active')
FOREACH (x IN CASE WHEN reopen THEN [sup] ELSE [] END | DELETE x)
SET n.valid_to = n.valid_from, n.status = 'superseded'
CREATE (n)-[:DUPLICATES {at: $now, reopened: reopen}]->(o)
DELETE l
RETURN n.id AS new_id, o.id AS old_id, reopen AS reopened, [mg IN fresh | mg.id] AS moved
