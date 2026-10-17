// name: lineage/link_step
// purpose: ONE atomic statement: attach what a Step read and wrote: (Step)-[:READ]->(Fact), (Step)-[:WROTE]->(Fact|Decision|Handoff|Task). All-or-nothing.
// params: step_id:str, read_ids:list[str], wrote_ids:list[str], via:str
// returns: step_id, n_read, n_wrote (zero rows = the Step or any referenced id does not exist; nothing written)
// mode: rw
// via ('use' | 'recall', D-012): 'use' = the agent acted on or cited the fact (decision, handoff, assert_fact duplicate/supersede/contradiction); the READ edge
// gets via and at = the Step's time. 'use' always wins on a re-MERGE (recall never downgrades a use); `at` only moves forward.
// Callers pass de-duplicated id lists of at most 200 ids each. MERGE keeps it idempotent (re-linking adds no edges).
// Empty-list form: `UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})` instead of `OPTIONAL MATCH (x:L) WHERE x.id IN $l`: on FalkorDB 6.0.2 an empty `IN $l` scans the whole id index of L (the '' placeholder seeks and matches nothing: no id is '').
MATCH (s:Step {id: $step_id})
UNWIND CASE WHEN size($read_ids) = 0 THEN [''] ELSE $read_ids END AS rid
OPTIONAL MATCH (rf:Fact {id: rid})
WITH s, collect(rf) AS reads
UNWIND CASE WHEN size($wrote_ids) = 0 THEN [''] ELSE $wrote_ids END AS wid
OPTIONAL MATCH (wf:Fact {id: wid})
WITH s, reads, collect(wf) AS wfs
UNWIND CASE WHEN size($wrote_ids) = 0 THEN [''] ELSE $wrote_ids END AS wid
OPTIONAL MATCH (wd:Decision {id: wid})
WITH s, reads, wfs, collect(wd) AS wds
UNWIND CASE WHEN size($wrote_ids) = 0 THEN [''] ELSE $wrote_ids END AS wid
OPTIONAL MATCH (wh:Handoff {id: wid})
WITH s, reads, wfs, wds, collect(wh) AS whs
UNWIND CASE WHEN size($wrote_ids) = 0 THEN [''] ELSE $wrote_ids END AS wid
OPTIONAL MATCH (wt:Task {id: wid})
WITH s, reads, wfs, wds, whs, collect(wt) AS wts
WITH s, reads, wfs + wds + whs + wts AS wrote
WHERE size(reads) = size($read_ids) AND size(wrote) = size($wrote_ids)
FOREACH (x IN reads |
  MERGE (s)-[rd:READ]->(x)
    ON CREATE SET rd.via = $via, rd.at = s.at
    ON MATCH SET rd.via = CASE WHEN rd.via = 'use' OR $via = 'use' THEN 'use' ELSE 'recall' END,
                 rd.at = CASE WHEN coalesce(rd.at, 0) > s.at THEN rd.at ELSE s.at END)
FOREACH (y IN wrote | MERGE (s)-[:WROTE]->(y))
RETURN s.id AS step_id, size(reads) AS n_read, size(wrote) AS n_wrote
