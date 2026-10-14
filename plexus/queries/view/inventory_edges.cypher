// name: view/inventory_edges
// purpose: Edge count per relationship type (the View's data inventory).
// params: none
// returns: type, n
// mode: ro
MATCH ()-[r]->()
RETURN type(r) AS type, count(r) AS n
ORDER BY type
