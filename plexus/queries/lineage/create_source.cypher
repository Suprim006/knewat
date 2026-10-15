// name: lineage/create_source
// purpose: MERGE a Source node (where a memory came from) keyed by its uri; idempotent, refreshes kind (and trust when given, title/text when non-empty).
// params: source_id:str, uri:str, kind:str, trust:str, title:str, text:str, now:int
// returns: id (the existing Source's id when the uri was already known, else source_id), created (bool)
// mode: rw
// trust is the STRING 'normal' | 'high' ('' = not given: a new Source is 'normal', an existing one keeps 'high' and anything else, e.g. a legacy float, becomes 'normal').
// Why a node: facts point at it with DERIVED_FROM, which is what forget_source / quarantine traverse.
MERGE (s:Source {uri: $uri})
  ON CREATE SET s.id = $source_id, s.kind = $kind, s.trust = CASE WHEN $trust = '' THEN 'normal' ELSE $trust END, s.title = $title, s.text = $text,
    s.created_at = $now, s.new = true
  ON MATCH SET s.kind = $kind, s.new = false,
    s.trust = CASE WHEN $trust <> '' THEN $trust WHEN s.trust = 'high' THEN 'high' ELSE 'normal' END,
    s.title = CASE WHEN $title = '' THEN coalesce(s.title, '') ELSE $title END,
    s.text = CASE WHEN $text = '' THEN coalesce(s.text, '') ELSE $text END
WITH s, s.new AS created
REMOVE s.new
RETURN s.id AS id, created
