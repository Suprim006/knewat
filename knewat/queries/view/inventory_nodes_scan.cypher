// name: view/inventory_nodes_scan
// purpose: Node count per label by scanning every node: complete for ANY label, O(nodes). The fallback when the graph holds a label view/inventory_nodes does not list.
// params: none
// returns: label, n
// mode: ro
MATCH (n)
RETURN labels(n)[0] AS label, count(n) AS n
ORDER BY label
