// name: relay/create_tasks
// purpose: Create a task DAG in ONE statement: all tasks, then all DEPENDS_ON edges, or nothing.
// params: tasks:list[map], edges:list[map], ids:list[str], ext_dep_ids:list[str] (de-duplicated), step_id:str ('' = none), now:int
// returns: edges (number of DEPENDS_ON edges created). Zero rows are never returned; when the guard fails
//   nothing is written, and the caller detects it from stats (nodes_created != len(tasks)).
// mode: rw
// step_id: the Step opened before this call; every created task is linked (Step)-[:WROTE]->(Task) in the same statement.
// Guard: no task id may exist yet, and every dependency outside the batch ($ext_dep_ids) must exist. It yields an empty $tasks to UNWIND rather than filtering rows, because an aggregation with no grouping key always returns one row.
// $ids is never empty (a batch has >= 1 task), so its `IN` is a seek; $ext_dep_ids is often empty, hence the UNWIND form below.
// Empty-list form: `UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})` instead of `WHERE x.id IN $l`: on 6.0.2 an empty `IN $l` scans the whole id index.
// $tasks items: {id, title, priority, seq} (seq = input position, FIFO tie-break). $edges items: {i, j, dep}: task index i depends on task index j of the same batch (j >= 0), or on the existing task id `dep` (j = -1). Caller bounds both (<= 500 tasks).
// Edges use list indexes because nodes created earlier in the same statement are NOT yet matchable by MATCH (6.0.2) but are usable through the collected list.
OPTIONAL MATCH (e:Task) WHERE e.id IN $ids
WITH collect(e.id) AS existing
UNWIND CASE WHEN size($ext_dep_ids) = 0 THEN [''] ELSE $ext_dep_ids END AS did
OPTIONAL MATCH (x:Task {id: did})
WITH existing, collect(x.id) AS found_ext
OPTIONAL MATCH (stp:Step {id: $step_id})
WITH stp, CASE WHEN size(existing) = 0 AND size(found_ext) = size($ext_dep_ids) THEN $tasks ELSE [] END AS to_create
UNWIND to_create AS row
CREATE (t:Task {
  id: row.id, title: row.title, status: 'open', priority: row.priority,
  lease_until: 0, claimed_by: '', version: 0, done_at: 0, created_at: $now, seq: row.seq
})
FOREACH (sw IN CASE WHEN stp IS NULL THEN [] ELSE [stp] END | CREATE (sw)-[:WROTE]->(t))
WITH collect(t) AS created
UNWIND $edges AS e
WITH created, e WHERE size(created) > 0
OPTIONAL MATCH (x:Task {id: e.dep})
WITH created[e.i] AS a, CASE WHEN e.j >= 0 THEN created[e.j] ELSE x END AS b
CREATE (a)-[r:DEPENDS_ON]->(b)
RETURN count(r) AS edges
