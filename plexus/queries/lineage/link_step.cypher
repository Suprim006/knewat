// name: lineage/link_step
// purpose: ONE atomic statement: attach what a Step read and wrote: (Step)-[:READ]->(Fact), (Step)-[:WROTE]->(Fact|Decision|Handoff|Task). All-or-nothing.
// params: step_id:str, read_ids:list[str], wrote_ids:list[str], via:str
// returns: step_id, n_read, n_wrote (zero rows = the Step or any referenced id does not exist; nothing written)
// mode: rw
// via ('use' | 'recall', D-012): 'use' = the agent acted on or cited the fact (decision, handoff, assert_fact duplicate/supersede/contradiction); the READ edge
// gets via and at = the Step's time. 'use' always wins on a re-MERGE (recall never downgrades a use); `at` only moves forward.
// Callers pass de-duplicated id lists of at most 200 ids each. MERGE keeps it idempotent (re-linking adds no edges).
MATCH (s:Step {id: $step_id})
OPTIONAL MATCH (rf:Fact) WHERE rf.id IN $read_ids
WITH s, collect(rf) AS reads
OPTIONAL MATCH (wf:Fact) WHERE wf.id IN $wrote_ids
WITH s, reads, collect(wf) AS wfs
OPTIONAL MATCH (wd:Decision) WHERE wd.id IN $wrote_ids
WITH s, reads, wfs, collect(wd) AS wds
OPTIONAL MATCH (wh:Handoff) WHERE wh.id IN $wrote_ids
WITH s, reads, wfs, wds, collect(wh) AS whs
OPTIONAL MATCH (wt:Task) WHERE wt.id IN $wrote_ids
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
