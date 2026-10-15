// name: lineage/record_recall
// purpose: ONE atomic statement: store a Recall (BY the agent, IN_STEP) with RETURNED{rank,score} edges to every returned Fact, and (Step)-[:READ]->(Fact) for each. All-or-nothing.
// params: recall_id:str, agent_id:str, step_id:str, query:str, scope_id:str, k:int, now:int,
//   fact_ids:list[str], results:list[map]
// returns: id, returned (number of facts linked). Zero rows = step_id is non-empty but unknown, or some fact id does not exist; nothing written.
// mode: rw
// READ provenance (D-012): the READ edge is created with via='recall' (surfaced, not acted on; weight 0.3 in the activation) and at=$now. One READ per (step, fact):
// on a re-MERGE a 'use' stays a 'use' and `at` moves forward. P7-04/10: READ.suspect = whether the fact was doubted AT that time by the contract rule (verify_state = 'suspect' OR verify_after <= $now); it moves with `at`. The activation model never counts a recall READ with suspect = true, however the fact is judged later. Edges written before P7 have no via/at and count as 'recall' at the Step's time.
// step_id is '' when the caller has no Step (then no IN_STEP / READ edges). results = [{fact_id, rank, score}], fact_ids = their de-duplicated ids (<= 200).
// The facts are matched first and their count compared with size($fact_ids) so a bad id writes nothing (same pattern as relay/handoff);
// the Agent MERGE comes after that guard, so a rejected call does not leave a new Agent behind (P5 review Q8).
OPTIONAL MATCH (st:Step {id: $step_id})
WITH st
WHERE $step_id = '' OR st IS NOT NULL
OPTIONAL MATCH (f:Fact) WHERE f.id IN $fact_ids
WITH st, collect(f) AS fs
WHERE size(fs) = size($fact_ids)
MERGE (a:Agent {id: $agent_id})
  ON CREATE SET a.name = $agent_id, a.created_at = $now
CREATE (r:Recall {id: $recall_id, at: $now, created_at: $now, query: $query, scope_id: $scope_id, agent_id: $agent_id, k: $k})
CREATE (r)-[:BY]->(a)
FOREACH (s IN CASE WHEN st IS NULL THEN [] ELSE [st] END | CREATE (r)-[:IN_STEP]->(s))
FOREACH (row IN $results |
  FOREACH (x IN [y IN fs WHERE y.id = row.fact_id] |
    CREATE (r)-[:RETURNED {rank: row.rank, score: row.score}]->(x)))
FOREACH (s IN CASE WHEN st IS NULL THEN [] ELSE [st] END |
  FOREACH (x IN fs |
    MERGE (s)-[rd:READ]->(x)
      ON CREATE SET rd.via = 'recall', rd.at = $now,
                    rd.suspect = (coalesce(x.verify_state, 'verified') = 'suspect' OR coalesce(x.verify_after, 9999999999999) <= $now)
      ON MATCH SET rd.via = CASE WHEN rd.via = 'use' THEN 'use' ELSE 'recall' END,
                   rd.suspect = CASE WHEN coalesce(rd.at, 0) > $now THEN rd.suspect
                                     ELSE (coalesce(x.verify_state, 'verified') = 'suspect' OR coalesce(x.verify_after, 9999999999999) <= $now) END,
                   rd.at = CASE WHEN coalesce(rd.at, 0) > $now THEN rd.at ELSE $now END))
RETURN r.id AS id, size(fs) AS returned
