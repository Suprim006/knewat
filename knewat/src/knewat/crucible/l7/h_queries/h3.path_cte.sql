-- H3 recursive CTE over paths (a path string for cycle safety), intermediate nodes active, shortest first
WITH RECURSIVE r(node, depth, path) AS (
  SELECT :a, 0, ',' || :a || ','
  UNION ALL
  SELECT fp.parent, r.depth + 1, r.path || fp.parent || ','
  FROM r JOIN facts cur ON cur.id = r.node JOIN fact_parent fp ON fp.child = r.node
  WHERE r.depth < 8 AND r.node <> :b AND (r.node = :a OR cur.status = 'active')
    AND instr(r.path, ',' || fp.parent || ',') = 0
)
SELECT path FROM r WHERE node = :b ORDER BY depth LIMIT 1
