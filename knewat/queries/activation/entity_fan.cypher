// name: activation/entity_fan
// purpose: The fan of a fact's entity (D-013 pattern separation): how many current (active) facts are ABOUT the same entity; memory_strength reports it with the entity lift a query naming the entity would give.
// params: fact_id:str
// returns: entity_id, name, fan (zero rows when the fact or its entity does not exist)
// mode: ro
// Plan shape: id index seek on the fact, then the entity's ABOUT edges (entity-first, like the sibling expansion of engram/recall).
MATCH (f:Fact {id: $fact_id})-[:ABOUT]->(e:Entity)
WITH e
MATCH (e)<-[:ABOUT]-(g:Fact {status: 'active'})
RETURN e.id AS entity_id, e.name AS name, count(g) AS fan
