// name: audit/record_tool_call
// purpose: Record one MCP tool call as a ToolCall node, attach it to its Step (when the Step exists) and link
//   it to the nodes the tool created/updated (CREATED/UPDATED edges). One bounded statement.
// params: id:str, tool:str, agent_id:str, step_id:str, step:int, query_name:str, run_time_ms:float, wrote:bool, links:list[map], now:int
// returns: id, links (number of CREATED/UPDATED edges written)
// mode: rw
// Runs as the statement right after the tool's own one (deviation from PLAN section 3), because run_time_ms is only known once that statement finished.
// $links items: {id, label, rel} with rel 'C' (CREATED) or 'U' (UPDATED); label is one of the whitelisted labels below (the Python wrapper drops anything else and caps the list at 200). Every lookup is a label+id index hit; an id that matches nothing gets no edge. An empty list is replaced by one inert row.
// $step_id '' means "no Step"; a Step id that does not exist just gets no IN_STEP edge.
CREATE (tc:ToolCall {
  id: $id, tool: $tool, at: $now, created_at: $now, agent_id: $agent_id, step: $step,
  query_name: $query_name, run_time_ms: $run_time_ms, wrote: $wrote
})
WITH tc
OPTIONAL MATCH (s:Step {id: $step_id})
FOREACH (_ IN CASE WHEN s IS NULL THEN [] ELSE [1] END | CREATE (tc)-[:IN_STEP]->(s))
WITH DISTINCT tc
UNWIND CASE WHEN size($links) = 0 THEN [{id: '', label: '', rel: ''}] ELSE $links END AS l
OPTIONAL MATCH (n1:Fact {id: l.id}) WHERE l.label = 'Fact'
OPTIONAL MATCH (n2:Episode {id: l.id}) WHERE l.label = 'Episode'
OPTIONAL MATCH (n3:Session {id: l.id}) WHERE l.label = 'Session'
OPTIONAL MATCH (n4:Entity {id: l.id}) WHERE l.label = 'Entity'
OPTIONAL MATCH (n5:Scope {id: l.id}) WHERE l.label = 'Scope'
OPTIONAL MATCH (n6:Task {id: l.id}) WHERE l.label = 'Task'
OPTIONAL MATCH (n7:Handoff {id: l.id}) WHERE l.label = 'Handoff'
OPTIONAL MATCH (n8:Artifact {id: l.id}) WHERE l.label = 'Artifact'
OPTIONAL MATCH (n9:Decision {id: l.id}) WHERE l.label = 'Decision'
OPTIONAL MATCH (n10:Run {id: l.id}) WHERE l.label = 'Run'
OPTIONAL MATCH (n11:Agent {id: l.id}) WHERE l.label = 'Agent'
OPTIONAL MATCH (n12:Procedure {id: l.id}) WHERE l.label = 'Procedure'
OPTIONAL MATCH (n13:Source {id: l.id}) WHERE l.label = 'Source'
OPTIONAL MATCH (n14:Recall {id: l.id}) WHERE l.label = 'Recall'
OPTIONAL MATCH (n15:Change {id: l.id}) WHERE l.label = 'Change'
OPTIONAL MATCH (n16:CodeAnchor {id: l.id}) WHERE l.label = 'CodeAnchor'
WITH tc, l, coalesce(n1, n2, n3, n4, n5, n6, n7, n8, n9, n10, n11, n12, n13, n14, n15, n16) AS n
FOREACH (_ IN CASE WHEN n IS NOT NULL AND l.rel = 'C' THEN [1] ELSE [] END | CREATE (tc)-[:CREATED]->(n))
FOREACH (_ IN CASE WHEN n IS NOT NULL AND l.rel = 'U' THEN [1] ELSE [] END | CREATE (tc)-[:UPDATED]->(n))
RETURN tc.id AS id, sum(CASE WHEN n IS NOT NULL THEN 1 ELSE 0 END) AS links
