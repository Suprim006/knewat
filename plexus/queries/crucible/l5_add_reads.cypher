// name: crucible/l5_add_reads
// purpose: L5 forgetting harness write: simulate reads. Creates the Steps and the (Step)-[:READ {via, at}]->(Fact) edges of a day of simulated use at the given times.
// params: reads:list[map{step_id,n,at,fact_id,via}], agent_id:str
// returns: n (READ edges created)
// mode: rw
// Benchmark harness only. Bounded by the size of $reads (callers send at most 1000 per call, LIMIT does not stop eager writes). Reads are simulated: the READ edge is exactly what the MCP tools write for a recall (via recall) or a use (via use).
UNWIND $reads AS r
MATCH (f:Fact {id: r.fact_id})
MERGE (s:Step {id: r.step_id})
  ON CREATE SET s.n = r.n, s.at = r.at, s.agent_id = $agent_id, s.created_at = r.at
CREATE (s)-[:READ {via: r.via, at: r.at}]->(f)
RETURN count(*) AS n
