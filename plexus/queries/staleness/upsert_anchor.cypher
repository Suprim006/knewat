// name: staleness/upsert_anchor
// purpose: ONE atomic statement: MERGE a CodeAnchor by its deterministic id (file / function / class of a repo) and link a Fact to it with ANCHORED_TO and/or a doc Source to it with DESCRIBES. Backs anchor_fact and describe_code.
// params: anchor_id:str, repo:str, path:str, symbol:str, kind:str, hash:str, fact_id:str, source_id:str, now:int
// returns: anchor_id, hash (the hash now stored on the anchor), created (bool). Zero rows = fact_id / source_id was given but does not exist (nothing is written, not even the anchor).
// mode: rw
// fact_id / source_id are '' when absent. An anchor that already has a hash keeps it (mark_changed is the only writer afterwards, so a hash given here can never hide a pending change); an anchor without one takes $hash and its updated_at moves. Linking is idempotent (MERGE on the edge, the first `at` is kept).
OPTIONAL MATCH (f:Fact {id: $fact_id})
OPTIONAL MATCH (s:Source {id: $source_id})
WITH f, s
WHERE ($fact_id = '' OR f IS NOT NULL) AND ($source_id = '' OR s IS NOT NULL)
OPTIONAL MATCH (prior:CodeAnchor {id: $anchor_id})
WITH f, s, prior IS NULL AS created
MERGE (a:CodeAnchor {id: $anchor_id})
  ON CREATE SET a.repo = $repo, a.path = $path, a.symbol = $symbol, a.kind = $kind, a.hash = $hash,
    a.updated_at = $now, a.created_at = $now
  ON MATCH SET a.updated_at = CASE WHEN coalesce(a.hash, '') = '' AND $hash <> '' THEN $now ELSE a.updated_at END,
    a.hash = CASE WHEN coalesce(a.hash, '') = '' AND $hash <> '' THEN $hash ELSE a.hash END,
    a.repo = CASE WHEN coalesce(a.repo, '') = '' THEN $repo ELSE a.repo END
FOREACH (x IN CASE WHEN f IS NULL THEN [] ELSE [f] END |
  MERGE (x)-[r:ANCHORED_TO]->(a) ON CREATE SET r.at = $now)
FOREACH (y IN CASE WHEN s IS NULL THEN [] ELSE [s] END |
  MERGE (y)-[d:DESCRIBES]->(a) ON CREATE SET d.at = $now)
RETURN a.id AS anchor_id, a.hash AS hash, created
