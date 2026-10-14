// name: view/inventory_nodes
// purpose: Node count per label (the View's data inventory).
// params: none
// returns: label, n
// mode: ro
MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS n
ORDER BY label
