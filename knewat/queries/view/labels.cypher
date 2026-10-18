// name: view/labels
// purpose: The node labels the graph has ever used (metadata, O(1)); the inventory compares them with the labels it counts directly.
// params: none
// returns: label
// mode: ro
CALL db.labels() YIELD label
RETURN label
ORDER BY label
