-- H1a shortcut triangle: a->b->c and a->c (fact_parent), three distinct asserting agents
WITH t AS (
  SELECT ab.child AS a, ab.parent AS b, bc.parent AS c
  FROM fact_parent ab
  JOIN fact_parent bc ON bc.child = ab.parent
  JOIN fact_parent ac ON ac.child = ab.child AND ac.parent = bc.parent
  JOIN facts fa ON fa.id = ab.child
  JOIN facts fb ON fb.id = ab.parent
  JOIN facts fc ON fc.id = bc.parent
  WHERE fa.agent_id <> fb.agent_id AND fb.agent_id <> fc.agent_id AND fa.agent_id <> fc.agent_id
)
SELECT (SELECT count(*) FROM t) AS n,
       (SELECT json_group_array(json_array(a, b, c)) FROM (SELECT * FROM t ORDER BY a, b, c LIMIT 5)) AS first
