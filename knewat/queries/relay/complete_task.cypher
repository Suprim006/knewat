// name: relay/complete_task
// purpose: Mark a claimed task done (compare-and-set on claimed_by + version) and record its artifacts.
// params: agent:str, task:str, expected_version:int, artifacts:list[map], artifact_ids:list[str], step_id:str ('' = none), now:int
// returns: id, status, version (zero rows = CAS rejected, or an artifact id already exists; nothing written)
// mode: rw
// step_id: the Step opened before this call; the task is linked (Step)-[:WROTE]->(Task) in the same statement.
// CAS: the task must be 'claimed', claimed_by = agent and version = expected_version. A duplicate artifact id rejects the whole call ($artifact_ids is used only for that guard). Artifacts are created inside FOREACH so an empty list keeps the row. $artifacts items: {id, kind, uri, hash, summary} ('' when absent).
// Each artifact gets (Artifact)-[:PRODUCED_BY]->(Agent) and (Artifact)-[:FOR]->(Task).
// Empty-list form: `UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})` instead of `WHERE x.id IN $l`: on 6.0.2 an empty `IN $l` scans the whole id index.
MATCH (t:Task {id: $task})
WHERE t.status = 'claimed' AND t.claimed_by = $agent AND t.version = $expected_version
MATCH (a:Agent {id: $agent})
OPTIONAL MATCH (stp:Step {id: $step_id})
UNWIND CASE WHEN size($artifact_ids) = 0 THEN [''] ELSE $artifact_ids END AS aid
OPTIONAL MATCH (e:Artifact {id: aid})
WITH a, t, stp, count(e) AS duplicates
WHERE duplicates = 0
SET t.status = 'done', t.done_at = $now, t.version = t.version + 1
FOREACH (art IN $artifacts |
  CREATE (x:Artifact {
    id: art.id, kind: art.kind, uri: art.uri, hash: art.hash, summary: art.summary,
    task_id: $task, created_at: $now
  })-[:PRODUCED_BY]->(a)
  CREATE (x)-[:FOR]->(t)
)
FOREACH (sw IN CASE WHEN stp IS NULL THEN [] ELSE [stp] END | CREATE (sw)-[:WROTE]->(t))
RETURN t.id AS id, t.status AS status, t.version AS version
