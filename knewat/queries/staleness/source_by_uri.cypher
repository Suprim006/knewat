// name: staleness/source_by_uri
// purpose: Find an existing Source by its uri (verify_fact reuses it as evidence instead of overwriting its kind / trust).
// params: uri:str
// returns: id, kind, trust. Zero rows = no such Source.
// mode: ro
MATCH (s:Source {uri: $uri})
RETURN s.id AS id, s.kind AS kind, s.trust AS trust
LIMIT 1
