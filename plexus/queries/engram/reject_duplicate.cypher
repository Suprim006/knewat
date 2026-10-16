// name: engram/reject_duplicate
// purpose: Say two facts are NOT duplicates: delete the (new)-[:DUPLICATES_MAYBE]->(old) soft link. Nothing else changes.
// params: new_id:str, old_id:str
// returns: removed (number of soft links deleted: 1, or 0 when there was none)
// mode: rw

MATCH (n:Fact {id: $new_id})-[l:DUPLICATES_MAYBE]->(o:Fact {id: $old_id})
DELETE l
RETURN count(l) AS removed
