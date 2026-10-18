// name: engram/entities_page
// purpose: One page of Entities in id order (keyset pagination) with the properties `knewat migrate entities` needs to backfill tok/num_key and to look for near-duplicates.
// params: after:str, limit:int
// returns: id, name, norm_name, kind, created_at, tok (null before the backfill), num_key (null before the backfill), embedding
// mode: ro
MATCH (e:Entity)
WHERE e.id > $after
WITH e ORDER BY e.id ASC LIMIT $limit
RETURN e.id AS id, e.name AS name, e.norm_name AS norm_name, e.kind AS kind, e.created_at AS created_at,
       e.tok AS tok, e.num_key AS num_key, e.embedding AS embedding
