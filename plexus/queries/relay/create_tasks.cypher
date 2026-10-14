// name: relay/create_tasks
// purpose: Create a task DAG in ONE statement: all tasks, then all DEPENDS_ON edges, or nothing.
// params: tasks:list[map], edges:list[map], ids:list[str], ext_dep_ids:list[str], now:int
// returns: edges (number of DEPENDS_ON edges created). Zero rows are never returned; when the guard fails
//   nothing is written, and the caller detects it from stats (nodes_created != len(tasks)).
// mode: rw
// Guard: no task id may exist yet, and every dependency outside the batch ($ext_dep_ids) must exist.
// The guard yields an empty $tasks to UNWIND (so nothing is created) rather than filtering rows, because an
// aggregation with no grouping key always returns one row.
// $tasks items: {id, title, priority}. $edges items: {i, j, dep}: task index i depends on task index j in the
// same batch (j >= 0), or on the already-existing task id `dep` (j = -1, dep != ''). Caller bounds both
// (<= 500 tasks). Edges use list indexes because nodes created earlier in the same statement are NOT yet
// matchable by MATCH (verified on 6.0.2) but are usable through the collected list.
OPTIONAL MATCH (e:Task) WHERE e.id IN $ids
WITH collect(e.id) AS existing
OPTIONAL MATCH (x:Task) WHERE x.id IN $ext_dep_ids
WITH existing, collect(x.id) AS found_ext
WITH CASE WHEN size(existing) = 0 AND size(found_ext) = size($ext_dep_ids) THEN $tasks ELSE [] END AS to_create
UNWIND to_create AS row
CREATE (t:Task {
  id: row.id, title: row.title, status: 'open', priority: row.priority,
  lease_until: 0, claimed_by: '', version: 0, done_at: 0, created_at: $now
})
WITH collect(t) AS created
UNWIND $edges AS e
WITH created, e WHERE size(created) > 0
OPTIONAL MATCH (x:Task {id: e.dep})
WITH created[e.i] AS a, CASE WHEN e.j >= 0 THEN created[e.j] ELSE x END AS b
CREATE (a)-[r:DEPENDS_ON]->(b)
RETURN count(r) AS edges
