// name: relay/fail_task
// purpose: Mark a claimed task failed (compare-and-set on claimed_by + version) and record its artifacts.
// params: agent:str, task:str, expected_version:int, artifacts:list[map], artifact_ids:list[str], reason:str, now:int
// returns: id, status, version (zero rows = CAS rejected, or an artifact id already exists; nothing written)
// mode: rw
// CAS: the task must be status 'claimed', claimed_by = agent and version = expected_version. The artifact id
// guard makes a duplicate artifact id reject the whole call. Artifacts are created inside FOREACH so an empty
// list does not remove the row. $artifacts items: {id, kind, uri, hash, summary} (no nulls; '' when absent).
// $artifact_ids is the list of those ids (used only for the duplicate guard).
// Each artifact gets (Artifact)-[:PRODUCED_BY]->(Agent) and (Artifact)-[:FOR]->(Task); the task_id property is kept too.
// Empty-list form: `UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})` instead of `OPTIONAL MATCH (x:L) WHERE x.id IN $l`: on FalkorDB 6.0.2 an empty `IN $l` scans the whole id index of L (the '' placeholder seeks and matches nothing: no id is '').
MATCH (t:Task {id: $task})
WHERE t.status = 'claimed' AND t.claimed_by = $agent AND t.version = $expected_version
MATCH (a:Agent {id: $agent})
UNWIND CASE WHEN size($artifact_ids) = 0 THEN [''] ELSE $artifact_ids END AS aid
OPTIONAL MATCH (e:Artifact {id: aid})
WITH a, t, count(e) AS duplicates
WHERE duplicates = 0
SET t.status = 'failed', t.fail_reason = $reason,
    t.done_at = $now, t.version = t.version + 1
FOREACH (art IN $artifacts |
  CREATE (x:Artifact {
    id: art.id, kind: art.kind, uri: art.uri, hash: art.hash, summary: art.summary,
    task_id: $task, created_at: $now
  })-[:PRODUCED_BY]->(a)
  CREATE (x)-[:FOR]->(t)
)
RETURN t.id AS id, t.status AS status, t.version AS version
