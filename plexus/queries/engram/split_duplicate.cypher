// name: engram/split_duplicate
// purpose: Undo confirm_duplicate: the new fact is current again, the old fact is closed again if the merge had reopened it, and the asserters the merge copied onto the old fact are removed.
// params: new_id:str, old_id:str, open_to:int
// returns: new_id, old_id, restored (true when the old fact was closed again); no row when the pair was not confirmed, or the facts moved on (the new fact is still zero-width, and a reopened old fact is still current)
// mode: rw

// The undo uses what confirm_duplicate stored: (new)-[:DUPLICATES {reopened}]->(old), and ASSERTED_BY.via = new.id on the edges the merge created.
MATCH (n:Fact {id: $new_id})-[d:DUPLICATES]->(o:Fact {id: $old_id})
WHERE n.valid_to = n.valid_from AND n.status = 'superseded'
  AND (NOT d.reopened OR (o.valid_to = $open_to AND o.status = 'active'))
OPTIONAL MATCH (o)-[moved:ASSERTED_BY {via: $new_id}]->(:Agent)
WITH n, d, o, d.reopened AS reopened, collect(moved) AS edges
FOREACH (m IN edges | DELETE m)
FOREACH (r IN CASE WHEN reopened THEN [o] ELSE [] END |
  SET r.valid_to = n.valid_from, r.status = 'superseded'
  CREATE (n)-[:SUPERSEDES]->(r))
SET n.valid_to = $open_to, n.status = 'active'
DELETE d
RETURN n.id AS new_id, o.id AS old_id, reopened AS restored
