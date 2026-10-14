// name: view/indexes
// purpose: The graph's indexes for the View inventory (label, properties, index types, status).
// params: none
// returns: label, properties, types, entitytype, status
// mode: ro
CALL db.indexes() YIELD label, properties, types, entitytype, status
RETURN label, properties, types, entitytype, status
ORDER BY label
