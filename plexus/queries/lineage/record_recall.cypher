// name: lineage/record_recall
// purpose: ONE atomic statement: store a Recall (BY the agent, IN_STEP) with RETURNED{rank,score} edges to every returned Fact, and (Step)-[:READ]->(Fact) for each. All-or-nothing.
// params: recall_id:str, agent_id:str, step_id:str, query:str, scope_id:str, k:int, now:int,
//   fact_ids:list[str], results:list[map]
// returns: id, returned (number of facts linked). Zero rows = step_id is non-empty but unknown, or some fact id does not exist; nothing written.
// mode: rw
// step_id is '' when the caller has no Step (then no IN_STEP / READ edges). results = [{fact_id, rank, score}], fact_ids = their de-duplicated ids (<= 200).
// The facts are matched first and their count compared with size($fact_ids) so a bad id writes nothing (same pattern as relay/handoff).
MERGE (a:Agent {id: $agent_id})
  ON CREATE SET a.name = $agent_id, a.created_at = $now
WITH a
OPTIONAL MATCH (st:Step {id: $step_id})
WITH a, st
WHERE $step_id = '' OR st IS NOT NULL
OPTIONAL MATCH (f:Fact) WHERE f.id IN $fact_ids
WITH a, st, collect(f) AS fs
WHERE size(fs) = size($fact_ids)
CREATE (r:Recall {id: $recall_id, at: $now, created_at: $now, query: $query, scope_id: $scope_id, agent_id: $agent_id, k: $k})
CREATE (r)-[:BY]->(a)
FOREACH (s IN CASE WHEN st IS NULL THEN [] ELSE [st] END | CREATE (r)-[:IN_STEP]->(s))
FOREACH (row IN $results |
  FOREACH (x IN [y IN fs WHERE y.id = row.fact_id] |
    CREATE (r)-[:RETURNED {rank: row.rank, score: row.score}]->(x)))
FOREACH (s IN CASE WHEN st IS NULL THEN [] ELSE [st] END |
  FOREACH (x IN fs | MERGE (s)-[:READ]->(x)))
RETURN r.id AS id, size(fs) AS returned
