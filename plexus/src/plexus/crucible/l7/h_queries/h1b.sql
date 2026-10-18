-- H1b handoff 3-cycle x->y->z->x of distinct agents (x = smallest id), each handoff carrying a fact
-- derived directly from one common source
WITH cyc AS (
  SELECT h1.from_agent AS x, h1.to_agent AS y, h2.to_agent AS z, h1.id AS h1, h2.id AS h2, h3.id AS h3
  FROM handoffs h1
  JOIN handoffs h2 ON h2.from_agent = h1.to_agent
  JOIN handoffs h3 ON h3.from_agent = h2.to_agent AND h3.to_agent = h1.from_agent
  WHERE h1.from_agent < h1.to_agent AND h1.from_agent < h2.to_agent AND h1.to_agent <> h2.to_agent
),
hs AS (
  SELECT hc.handoff_id AS h, fs.source_id AS s
  FROM handoff_carries hc JOIN fact_source fs ON fs.fact_id = hc.fact_id
),
t AS (
  SELECT DISTINCT cyc.x, cyc.y, cyc.z
  FROM cyc
  JOIN hs a ON a.h = cyc.h1
  JOIN hs b ON b.h = cyc.h2 AND b.s = a.s
  JOIN hs c ON c.h = cyc.h3 AND c.s = a.s
)
SELECT (SELECT count(*) FROM t) AS n,
       (SELECT json_group_array(json_array(x, y, z)) FROM (SELECT * FROM t ORDER BY x, y, z LIMIT 5)) AS first
