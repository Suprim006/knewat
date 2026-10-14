// name: engram/start_session
// purpose: MERGE the Agent, create a Session and the (Agent)-[:HAD]->(Session) edge in one statement.
// params: agent_id:str, agent_role:str, harness:str, session_id:str, now:int
// returns: session_id, agent_id
// mode: rw
MERGE (ag:Agent {id: $agent_id})
  ON CREATE SET ag.name = $agent_id, ag.created_at = $now
SET ag.role = $agent_role, ag.harness = $harness
CREATE (s:Session {id: $session_id, agent_id: $agent_id, started_at: $now, ended_at: 9999999999999, created_at: $now})
CREATE (ag)-[:HAD]->(s)
RETURN s.id AS session_id, ag.id AS agent_id
