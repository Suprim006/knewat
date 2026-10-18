// name: view/relationship_types
// purpose: The relationship types the graph has ever used (metadata, O(1)); the inventory compares them with the types it counts directly.
// params: none
// returns: type
// mode: ro
CALL db.relationshipTypes() YIELD relationshipType
RETURN relationshipType AS type
ORDER BY type
