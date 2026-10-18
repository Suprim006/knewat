-- H3 recursive CTE that keeps one row per (node, depth) (UNION dedupes): polynomial, gives the length only
WITH RECURSIVE r(node, depth) AS (
  SELECT :a, 0
  UNION
  SELECT fp.parent, r.depth + 1
  FROM r JOIN facts cur ON cur.id = r.node JOIN fact_parent fp ON fp.child = r.node
  WHERE r.depth < 8 AND r.node <> :b AND (r.node = :a OR cur.status = 'active')
)
SELECT min(depth) AS depth FROM r WHERE node = :b
