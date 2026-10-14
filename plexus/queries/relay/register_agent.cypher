// name: relay/register_agent
// purpose: Create the Agent node, or refresh its name/role/harness (idempotent on id).
// params: id:str, name:str, role:str, harness:str, now:int
// returns: id, name, role, harness
// mode: rw
MERGE (a:Agent {id: $id})
ON CREATE SET a.created_at = $now
SET a.name = $name, a.role = $role, a.harness = $harness
RETURN a.id AS id, a.name AS name, a.role AS role, a.harness AS harness
