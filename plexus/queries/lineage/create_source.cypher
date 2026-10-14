// name: lineage/create_source
// purpose: MERGE a Source node (where a memory came from) keyed by its uri; idempotent, refreshes kind/trust (and title/text when non-empty).
// params: source_id:str, uri:str, kind:str, trust:float, title:str, text:str, now:int
// returns: id (the existing Source's id when the uri was already known, else source_id), created (bool)
// mode: rw
// Why a node: facts point at it with DERIVED_FROM, which is what forget_source / quarantine traverse.
MERGE (s:Source {uri: $uri})
  ON CREATE SET s.id = $source_id, s.kind = $kind, s.trust = $trust, s.title = $title, s.text = $text,
    s.created_at = $now, s.new = true
  ON MATCH SET s.kind = $kind, s.trust = $trust, s.new = false,
    s.title = CASE WHEN $title = '' THEN coalesce(s.title, '') ELSE $title END,
    s.text = CASE WHEN $text = '' THEN coalesce(s.text, '') ELSE $text END
WITH s, s.new AS created
REMOVE s.new
RETURN s.id AS id, created
