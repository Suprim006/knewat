// name: l2/facts_from_source
// purpose: facts that reach a Source through DERIVED_FROM, with their status.
// params: uri:str
// returns: predicate, value, status
// mode: ro
MATCH (f:Fact)-[:DERIVED_FROM*1..5]->(:Source {uri: $uri})
RETURN DISTINCT f.predicate AS predicate, f.value AS value, f.status AS status
ORDER BY predicate ASC, value ASC
