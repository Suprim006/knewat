// name: view/step_agents
// purpose: The agents that have taken a Step numbered <= $n (the step slider asks "what did each agent know at step n?"); the answer per agent is Lineage.knew_at.
// params: n:int
// returns: agent_id (one row per agent, sorted)
// mode: ro
// Needs Lineage's Step nodes (graph model v1); a graph without Steps returns no rows. Bounded by the number of agents.
MATCH (s:Step) WHERE s.n <= $n
RETURN DISTINCT s.agent_id AS agent_id
ORDER BY agent_id
LIMIT 200
