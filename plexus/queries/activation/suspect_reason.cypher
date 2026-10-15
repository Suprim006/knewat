// name: activation/suspect_reason
// purpose: For recall rows of suspect facts: the newest Change that SUSPECTED each fact (commit, time, paths), so the row can say why it is doubted.
// params: fact_ids:list[str]
// returns: fact_id, commit ('' = a working-tree change, or no Change at all), at (0 when no Change), paths (the Change.paths JSON string, '' when no Change), has_change (false = the fact was marked suspect without a Change node)
// mode: ro

// P7-J creates (Change)-[:SUSPECTED]->(Fact); this query only reads it. On 6.0.2 an OPTIONAL MATCH over a label or relationship type that does not exist yet
// returns no match instead of failing, so the query is safe on a graph that never had a Change (tests/activation/test_recall_rerank.py uses hand-made Changes).
// At most ~50 ids (the rows recall returns); one index seek per id; the newest Change wins (ORDER BY at DESC, the first of the collected list).
UNWIND $fact_ids AS fid
MATCH (f:Fact {id: fid})
OPTIONAL MATCH (c:Change)-[:SUSPECTED]->(f)
WITH f, c ORDER BY c.at DESC
WITH f, collect(c) AS cs
RETURN f.id AS fact_id,
       CASE WHEN size(cs) = 0 THEN '' ELSE coalesce(cs[0].commit, '') END AS commit,
       CASE WHEN size(cs) = 0 THEN 0 ELSE coalesce(cs[0].at, 0) END AS at,
       CASE WHEN size(cs) = 0 THEN '' ELSE coalesce(cs[0].paths, '') END AS paths,
       size(cs) > 0 AS has_change
