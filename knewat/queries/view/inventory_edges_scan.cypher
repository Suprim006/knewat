// name: view/inventory_edges_scan
// purpose: Edge count per relationship type by scanning every edge: complete for ANY type, O(edges). The fallback when the graph holds a type view/inventory_edges does not list.
// params: none
// returns: type, n
// mode: ro
MATCH ()-[r]->()
RETURN type(r) AS type, count(r) AS n
ORDER BY type
