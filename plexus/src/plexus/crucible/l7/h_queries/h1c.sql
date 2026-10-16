-- H1c independent corroboration: two active facts, same subject+predicate, different agents,
-- derived directly from different sources, neither derived from the other at any depth
WITH RECURSIVE cand AS (
  SELECT f1.id AS a, f2.id AS b
  FROM facts f1
  JOIN fact_source s1 ON s1.fact_id = f1.id
  JOIN facts f2 ON f2.subject = f1.subject AND f2.predicate = f1.predicate AND f2.id > f1.id
  JOIN fact_source s2 ON s2.fact_id = f2.id
  WHERE f1.status = 'active' AND f2.status = 'active'
    AND s1.source_id <> s2.source_id AND f1.agent_id <> f2.agent_id
),
up(a, b, side, node) AS (
  SELECT a, b, 0, a FROM cand
  UNION SELECT a, b, 1, b FROM cand
  UNION SELECT up.a, up.b, up.side, fp.parent FROM up JOIN fact_parent fp ON fp.child = up.node
),
t AS (
  SELECT a, b FROM cand
  EXCEPT SELECT a, b FROM up WHERE (side = 0 AND node = b) OR (side = 1 AND node = a)
)
SELECT (SELECT count(*) FROM t) AS n,
       (SELECT json_group_array(json_array(a, b)) FROM (SELECT * FROM t ORDER BY a, b LIMIT 5)) AS first
