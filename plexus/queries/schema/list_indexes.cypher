// name: schema/list_indexes
// purpose: List the graph's indexes (label, properties, per-property index types, status) for verification and the View inventory.
// params: none
// returns: label, properties, types (map property -> [RANGE|FULLTEXT|VECTOR]), options, language, stopwords, entitytype, status, info
// mode: ro
CALL db.indexes()
