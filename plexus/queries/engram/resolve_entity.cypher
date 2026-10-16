// name: engram/resolve_entity
// purpose: Atomic resolve-or-create of an Entity: exact norm_name, then full-text (OR over the name tokens, token Jaccard), then vector nearest, then MERGE on norm_name; one write statement, so no other creator can interleave between the lookups and the create.
// params: norm:str, name:str, kind:str, tok:list[str], num_key:str, q:str, emb:list[float], entity_id:str, jac:float, thr:float, k:int, now:int
// returns: id, name, kind, how ('exact' | 'fulltext' | 'vector' | 'new'); exactly one row
// mode: rw
// Why one statement: FalkorDB serialises writes per graph, and the two candidate lookups (CALL subqueries) run inside the write, so a
// paraphrase cannot slip in between the lookup and the create (the old flow did 3 reads, then a MERGE). Each lookup is wrapped in
// CALL { ... RETURN collect(node) } because a bare CALL that yields 0 rows empties the row set and the later clauses (and the create)
// would be skipped. The full-text query is q = 'a|b|c' (OR): with AND an older, shorter name was missed, so resolution depended on
// creation order. Candidates must have the same kind and the same num_key (numbers/versions) and are ranked by Jaccard (tok) / distance,
// ties by (created_at, id) so the outcome is deterministic. Entities without tok/num_key (pre-migration) never match the fuzzy lookups; run
// `plexus migrate entities` first. MERGE stays the create (not CREATE) so the UNIQUE(Entity.norm_name) constraint and MERGE agree.
CALL {
  CALL db.idx.fulltext.queryNodes('Entity', $q) YIELD node
  WHERE node.kind = $kind AND node.num_key = $num_key
  WITH node, size([t IN $tok WHERE t IN node.tok]) AS inter
  WITH node, toFloat(inter) / (size($tok) + size(node.tok) - inter) AS j
  WHERE j >= $jac
  WITH node ORDER BY j DESC, node.created_at ASC, node.id ASC
  RETURN collect(node) AS ft
}
CALL {
  CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($emb)) YIELD node, score
  WHERE node.kind = $kind AND node.num_key = $num_key AND score <= $thr
  WITH node, score ORDER BY score ASC, node.created_at ASC, node.id ASC
  RETURN collect(node) AS vec
}
OPTIONAL MATCH (ex:Entity {norm_name: $norm})
WITH coalesce(ex, head(ft), head(vec)) AS hit,
     CASE WHEN ex IS NOT NULL THEN 'exact' WHEN size(ft) > 0 THEN 'fulltext'
          WHEN size(vec) > 0 THEN 'vector' ELSE 'new' END AS how
FOREACH (_ IN CASE WHEN hit IS NULL THEN [1] ELSE [] END |
  MERGE (n:Entity {norm_name: $norm})
    ON CREATE SET n.id = $entity_id, n.name = $name, n.kind = $kind, n.num_key = $num_key,
                  n.tok = $tok, n.embedding = vecf32($emb), n.created_at = $now)
RETURN CASE WHEN hit IS NULL THEN $entity_id ELSE hit.id END AS id,
       CASE WHEN hit IS NULL THEN $name ELSE hit.name END AS name,
       CASE WHEN hit IS NULL THEN $kind ELSE hit.kind END AS kind,
       how
