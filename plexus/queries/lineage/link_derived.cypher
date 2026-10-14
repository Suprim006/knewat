// name: lineage/link_derived
// purpose: ONE atomic statement: record that a Fact was derived from other nodes: (Fact)-[:DERIVED_FROM]->(Source|Episode|Fact). All-or-nothing.
// params: fact_id:str, from_ids:list[str]
// returns: id, linked (zero rows = the fact or any source id does not exist; nothing written)
// mode: rw
// Used for consolidated / inferred facts. forget_source and quarantine follow these edges (DERIVED_FROM*1..5) to find everything downstream of a bad source.
// from_ids are de-duplicated by the caller (<= 100); a fact cannot derive from itself (checked in Python).
MATCH (f:Fact {id: $fact_id})
OPTIONAL MATCH (s:Source) WHERE s.id IN $from_ids
WITH f, collect(s) AS ss
OPTIONAL MATCH (e:Episode) WHERE e.id IN $from_ids
WITH f, ss, collect(e) AS es
OPTIONAL MATCH (g:Fact) WHERE g.id IN $from_ids
WITH f, ss, es, collect(g) AS gs
WITH f, ss + es + gs AS srcs
WHERE size(srcs) = size($from_ids)
FOREACH (x IN srcs | MERGE (f)-[:DERIVED_FROM]->(x))
RETURN f.id AS id, size(srcs) AS linked
