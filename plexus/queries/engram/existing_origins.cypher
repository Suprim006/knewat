// name: engram/existing_origins
// purpose: Which of the given ids name a Fact, a Source or an Episode (the nodes a fact may be DERIVED_FROM).
// params: ids:list[str]
// returns: id, label (one row per id that exists; missing ids have no row)
// mode: ro
// P9-f: Engram.assert_fact checks its derived_from origins with this before it creates a new subject Entity, so a bad
// origin id is rejected with nothing written (the assert_fact statement itself re-checks them and writes nothing either).
MATCH (n:Fact) WHERE n.id IN $ids RETURN n.id AS id, 'Fact' AS label
UNION
MATCH (n:Source) WHERE n.id IN $ids RETURN n.id AS id, 'Source' AS label
UNION
MATCH (n:Episode) WHERE n.id IN $ids RETURN n.id AS id, 'Episode' AS label
