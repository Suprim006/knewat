-- H2 for agent :agent: pairs (D, f) where the agent decided D, D based on g, g derived from f in 0..:n hops,
-- and a step by the agent read f before D
WITH RECURSIVE r(d, at, f, k) AS (
  SELECT dec.id, dec.at, b.fact_id, 0
  FROM decisions dec JOIN decision_based_on b ON b.decision_id = dec.id
  WHERE dec.agent_id = :agent
  UNION
  SELECT r.d, r.at, fp.parent, r.k + 1 FROM r JOIN fact_parent fp ON fp.child = r.f WHERE r.k < :n
),
t AS (
  SELECT DISTINCT r.d, r.f FROM r
  WHERE EXISTS (SELECT 1 FROM steps s JOIN step_reads sr ON sr.step_id = s.id
                WHERE s.agent_id = :agent AND sr.fact_id = r.f AND s.at < r.at)
)
SELECT (SELECT count(*) FROM t) AS n,
       (SELECT json_group_array(json_array(d, f)) FROM (SELECT * FROM t ORDER BY d, f LIMIT 5)) AS first
