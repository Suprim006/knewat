// name: lineage/link_derived
// purpose: ONE atomic statement: record that a Fact was derived from other nodes: (Fact)-[:DERIVED_FROM]->(Source|Episode|Fact). All-or-nothing.
// params: fact_id:str, from_ids:list[str]
// returns: id, linked (zero rows = the fact or any source id does not exist; nothing written)
// mode: rw
// Used for consolidated / inferred facts. forget_source and quarantine follow these edges level by level up to $depth (1..12) to find everything downstream of a bad source.
// from_ids are de-duplicated by the caller (<= 100); a fact cannot derive from itself (checked in Python).
// Empty-list form: `UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})` instead of `OPTIONAL MATCH (x:L) WHERE x.id IN $l`: on FalkorDB 6.0.2 an empty `IN $l` scans the whole id index of L (the '' placeholder seeks and matches nothing: no id is '').
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
