// name: schema/list_constraints
// purpose: List the graph's constraints with their build status (PENDING/UNDER CONSTRUCTION/OPERATIONAL/FAILED).
// params: none
// returns: type, label, properties, entitytype, status
// mode: ro
CALL db.constraints()
