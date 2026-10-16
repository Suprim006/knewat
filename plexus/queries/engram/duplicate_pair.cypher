// name: engram/duplicate_pair
// purpose: The state of one (new, old) fact pair for confirm_duplicate / reject_duplicate: does the soft link exist, was it already confirmed, and are the two facts still in a state that allows a merge or an undo.
// params: new_id:str, old_id:str, open_to:int
// returns: no row when either fact does not exist; else new_id, old_id, linked (a DUPLICATES_MAYBE edge new->old exists), confirmed (a DUPLICATES edge new->old exists), new_current (new is the open-ended current fact), old_current (old is the open-ended current fact), old_reopenable (new SUPERSEDES old and old is still closed at new.valid_from), same_entity (both are about the same entity + predicate + scope)
// mode: ro

MATCH (n:Fact {id: $new_id})
MATCH (o:Fact {id: $old_id})
RETURN n.id AS new_id, o.id AS old_id,
       size([(n)-[:DUPLICATES_MAYBE]->(o) | 1]) > 0 AS linked,
       size([(n)-[:DUPLICATES]->(o) | 1]) > 0 AS confirmed,
       (n.valid_to = $open_to AND n.status IN ['active', 'dormant']) AS new_current,
       (o.valid_to = $open_to AND o.status IN ['active', 'dormant']) AS old_current,
       (size([(n)-[:SUPERSEDES]->(o) | 1]) > 0 AND o.status = 'superseded' AND o.valid_to = n.valid_from) AS old_reopenable,
       (n.subject_id = o.subject_id AND n.predicate = o.predicate) AS same_entity
