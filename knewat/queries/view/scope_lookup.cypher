// name: view/scope_lookup
// purpose: Look up an existing Scope by id, or by (kind, name), without creating it; read tools use it so a typo in `scope` never grows the graph.
// params: id:str, kind:str, name:str
// returns: id, kind, name (zero or one row; zero rows = no such scope)
// mode: ro
// Pass id = '' to look up by (kind, name); pass kind = '' and name = '' to look up by id.
MATCH (s:Scope)
WHERE ($id <> '' AND s.id = $id) OR ($id = '' AND s.kind = $kind AND s.name = $name)
RETURN s.id AS id, s.kind AS kind, s.name AS name
LIMIT 1
