// name: engram/missing_refs
// purpose: Which of a scope / episode / source id exist (explains a rejected assert_fact).
// params: scope_id:str, episode_id:str, source_id:str ('' = not given)
// returns: scopes, episodes, sources (match counts; 0 = missing)
// mode: ro
OPTIONAL MATCH (sc:Scope {id: $scope_id})
WITH count(sc) AS scopes
OPTIONAL MATCH (ep:Episode {id: $episode_id})
WITH scopes, count(ep) AS episodes
OPTIONAL MATCH (src:Source {id: $source_id})
RETURN scopes, episodes, count(src) AS sources
