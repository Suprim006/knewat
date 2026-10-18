// name: engram/backfill_entity_keys
// purpose: Set Entity.tok and Entity.num_key on existing entities (one batch; the caller sends at most 200 rows per statement).
// params: rows:list[map]
// returns: n (entities updated)
// mode: rw
UNWIND $rows AS row
MATCH (e:Entity {id: row.id})
SET e.tok = row.tok, e.num_key = row.num_key
RETURN count(e) AS n
