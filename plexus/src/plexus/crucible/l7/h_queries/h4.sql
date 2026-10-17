-- H4 per source: distinct agents with a decision that depends on it at any depth
WITH RECURSIVE r(agent, f) AS (
  SELECT DISTINCT d.agent_id, b.fact_id FROM decisions d JOIN decision_based_on b ON b.decision_id = d.id
  UNION
  SELECT r.agent, fp.parent FROM r JOIN fact_parent fp ON fp.child = r.f
)
SELECT fs.source_id AS s, count(DISTINCT r.agent) AS n
FROM r JOIN fact_source fs ON fs.fact_id = r.f
GROUP BY fs.source_id ORDER BY n DESC, fs.source_id LIMIT 10
