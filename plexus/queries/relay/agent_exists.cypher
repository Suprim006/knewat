// name: relay/agent_exists
// purpose: Does an Agent with this id exist (explains an empty claim result).
// params: id:str
// returns: id (zero rows when unknown)
// mode: ro
MATCH (a:Agent {id: $id})
RETURN a.id AS id
