// name: l2/active_conflicts
// purpose: active facts that CONTRADICT another active fact, with asserting agents and source uris.
// params: none
// returns: predicate, value, asserted_by [agent ids], sources [uris]
// mode: ro
MATCH (f:Fact)-[:CONTRADICTS]-(g:Fact)
WHERE f.status = 'active' AND g.status = 'active'
RETURN DISTINCT f.predicate AS predicate, f.value AS value,
       [(f)-[:ASSERTED_BY]->(a:Agent) | a.id] AS asserted_by,
       [(f)-[:DERIVED_FROM]->(s:Source) | s.uri] AS sources
ORDER BY predicate ASC, value ASC
