// name: view/maybe_duplicates
// purpose: For the facts in the explorer subgraph: the older fact each one is a possible duplicate of (the P9-c soft link (new)-[:DUPLICATES_MAYBE]->(old), not yet confirmed or rejected).
// params: ids:list[str]
// returns: id (the new fact), other (the older fact it may duplicate), score (1 - cosine distance at write time); nearest first, at most 5 per fact
// mode: ro
// The fact is bound by its id index first (one Node By Index Scan per id) and only then expanded: `UNWIND ids ... MATCH (f:Fact {id: x})-[r]->()` in one pattern walks every DUPLICATES_MAYBE edge.
UNWIND CASE WHEN size($ids) = 0 THEN [''] ELSE $ids END AS x
MATCH (f:Fact {id: x})
WITH f
MATCH (f)-[r:DUPLICATES_MAYBE]->(o:Fact)
RETURN f.id AS id, o.id AS other, r.score AS score
ORDER BY id, score DESC, other
