// name: engram/recall_keywords
// purpose: Keyword channel of recall: ids of in-scope, currently valid facts whose Fact.value or Fact.search_text (entity name + predicate words, P12) matches any of the query words (full-text index), best match first.
// params: text:str, scope_id:str, all:bool, k:int, t:int, statuses:list[str]
// (text is RediSearch syntax: words joined by a pipe = OR)
// returns: id (fact id), score (full-text relevance, higher = better); at most k rows
// mode: ro

// Unlike the vector seeds this filters BEFORE the LIMIT, so out-of-scope or superseded facts cannot starve the result.
// engram/recall unions these ids into its seeds; their order here is the keyword rank of the fusion. $all = every scope (recall scope 'all').
MATCH (:Scope {id: $scope_id})-[:INHERITS*0..3]->(a:Scope)
WITH collect(DISTINCT a.id) AS sids
CALL db.idx.fulltext.queryNodes('Fact', $text) YIELD node, score
WITH sids, node AS f, score
WHERE f.status IN $statuses AND f.valid_from <= $t AND $t < f.valid_to
MATCH (f)-[:IN_SCOPE]->(fs:Scope)
WHERE $all OR fs.id IN sids
RETURN DISTINCT f.id AS id, score
ORDER BY score DESC, id ASC
LIMIT $k
