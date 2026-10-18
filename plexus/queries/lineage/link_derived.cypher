// name: lineage/link_derived
// purpose: ONE atomic statement: record that a Fact was derived from other nodes, (Fact)-[:DERIVED_FROM]->(Source|Episode|Fact). All-or-nothing. forget_source and quarantine follow these edges.
// params: fact_id:str, from_ids:list[str]
// returns: id, linked (zero rows = the fact or any origin id does not exist; nothing written)
// mode: rw
// from_ids are de-duplicated by the caller (<= 100); a fact cannot derive from itself (checked in Python).
// Empty-list form: `UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})` instead of `WHERE x.id IN $l`: on 6.0.2 an empty `IN $l` scans the whole id index.
MATCH (f:Fact {id: $fact_id})
UNWIND CASE WHEN size($from_ids) = 0 THEN [''] ELSE $from_ids END AS sid
OPTIONAL MATCH (s:Source {id: sid})
WITH f, collect(s) AS ss
UNWIND CASE WHEN size($from_ids) = 0 THEN [''] ELSE $from_ids END AS eid
OPTIONAL MATCH (e:Episode {id: eid})
WITH f, ss, collect(e) AS es
UNWIND CASE WHEN size($from_ids) = 0 THEN [''] ELSE $from_ids END AS gid
OPTIONAL MATCH (g:Fact {id: gid})
WITH f, ss, es, collect(g) AS gs
WITH f, ss + es + gs AS srcs
WHERE size(srcs) = size($from_ids)
FOREACH (x IN srcs | MERGE (f)-[:DERIVED_FROM]->(x))
RETURN f.id AS id, size(srcs) AS linked
