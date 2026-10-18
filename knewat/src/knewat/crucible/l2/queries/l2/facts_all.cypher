// name: l2/facts_all
// purpose: every Fact with its scope, status, asserting agents, source uris and the facts it SUPERSEDES.
// params: none
// returns: predicate, value, status, scope_kind, scope_name, asserted_by [agent ids], sources [uris], supersedes [{predicate, value}]
// mode: ro
MATCH (f:Fact)-[:IN_SCOPE]->(s:Scope)
RETURN f.predicate AS predicate, f.value AS value, f.status AS status, s.kind AS scope_kind, s.name AS scope_name,
       [(f)-[:ASSERTED_BY]->(a:Agent) | a.id] AS asserted_by,
       [(f)-[:DERIVED_FROM]->(x:Source) | x.uri] AS sources,
       [(f)-[:SUPERSEDES]->(o:Fact) | {predicate: o.predicate, value: o.value}] AS supersedes
ORDER BY f.valid_from ASC, f.value ASC
