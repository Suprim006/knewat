// name: engram/assert_fact
// purpose: ONE atomic statement: classify the new assertion against the current facts of the same entity+predicate+scope (duplicate / supersede / contradiction), then write it with provenance.
// params: entity_id:str, predicate:str, value:str, norm_value:str, scope_id:str, agent_id:str,
//   source_id:str, episode_id:str, confidence:float, supersede:bool, now:int, open_to:int,
//   fact_id:str, emb:list[float], value_emb:list[float], dup_threshold:float
// returns: fact_id (the new fact, or the existing duplicate), duplicate_of (id or null), superseded (ids), contradicts (ids); no row when the entity or scope does not exist
// mode: rw

// Rules, evaluated on facts with status='active' and valid_to=open_to in the same scope:
//   dup        = first current fact with the same norm_value, else with value_emb within dup_threshold (cosine distance)
//   dup found  -> no new Fact; MERGE (dup)-[:ASSERTED_BY]->agent (+ DERIVED_FROM episode/source)
//   otherwise  -> closing   = current facts asserted only by this agent, or all of them when supersede=true
//                 clashing  = the remaining current facts (other agents' view)
//                 new Fact; closing get valid_to=now,status='superseded' + (new)-[:SUPERSEDES]->(old); clashing get (new)-[:CONTRADICTS]->(old) and stay active
// source_id / episode_id are '' when absent. Source nodes are Lineage's: the DERIVED_FROM edge is only made if the node exists.
// Lineage tail: everything that follows the FOREACH is a plain RETURN; to log a Step, put `MATCH (st:Step {id: $step_id})` before the
//   FOREACHes and add `CREATE (st)-[:WROTE]->(nf)` inside the new-fact FOREACH (and `(st)-[:READ]->(x)` for dup/closing), then keep the RETURN.
MERGE (ag:Agent {id: $agent_id})
  ON CREATE SET ag.name = $agent_id, ag.created_at = $now
WITH ag
MATCH (e:Entity {id: $entity_id}), (sc:Scope {id: $scope_id})
OPTIONAL MATCH (ep:Episode {id: $episode_id})
OPTIONAL MATCH (src:Source {id: $source_id})
OPTIONAL MATCH (f:Fact {subject_id: $entity_id, predicate: $predicate, status: 'active', valid_to: $open_to})-[:IN_SCOPE]->(sc)
WITH ag, e, sc, ep, src, collect(f) AS cur
WITH ag, e, sc, ep, src, cur,
     head([x IN cur WHERE x.norm_value = $norm_value]
          + [x IN cur WHERE vec.cosineDistance(x.value_embedding, vecf32($value_emb)) <= $dup_threshold]) AS dup
WITH ag, e, sc, ep, src, dup,
     CASE WHEN dup IS NULL THEN
       [x IN cur WHERE $supersede OR all(a IN [(x)-[:ASSERTED_BY]->(o:Agent) | o.id] WHERE a = $agent_id)]
     ELSE [] END AS closing,
     CASE WHEN dup IS NULL THEN
       [x IN cur WHERE NOT ($supersede OR all(a IN [(x)-[:ASSERTED_BY]->(o:Agent) | o.id] WHERE a = $agent_id))]
     ELSE [] END AS clashing
FOREACH (d IN CASE WHEN dup IS NULL THEN [] ELSE [dup] END |
  MERGE (d)-[:ASSERTED_BY]->(ag)
  FOREACH (x IN CASE WHEN ep IS NULL THEN [] ELSE [ep] END | MERGE (d)-[:DERIVED_FROM]->(x))
  FOREACH (x IN CASE WHEN src IS NULL THEN [] ELSE [src] END | MERGE (d)-[:DERIVED_FROM]->(x)))
FOREACH (_ IN CASE WHEN dup IS NULL THEN [1] ELSE [] END |
  CREATE (nf:Fact {id: $fact_id, subject_id: $entity_id, predicate: $predicate, value: $value, norm_value: $norm_value,
                   valid_from: $now, valid_to: $open_to, recorded_at: $now, created_at: $now, status: 'active',
                   confidence: $confidence, embedding: vecf32($emb), value_embedding: vecf32($value_emb)})
  CREATE (nf)-[:ABOUT]->(e)
  CREATE (nf)-[:IN_SCOPE]->(sc)
  CREATE (nf)-[:ASSERTED_BY]->(ag)
  FOREACH (x IN CASE WHEN ep IS NULL THEN [] ELSE [ep] END | CREATE (nf)-[:DERIVED_FROM]->(x))
  FOREACH (x IN CASE WHEN src IS NULL THEN [] ELSE [src] END | CREATE (nf)-[:DERIVED_FROM]->(x))
  FOREACH (c IN closing | SET c.valid_to = $now, c.status = 'superseded' CREATE (nf)-[:SUPERSEDES]->(c))
  FOREACH (c IN clashing | CREATE (nf)-[:CONTRADICTS]->(c)))
RETURN CASE WHEN dup IS NULL THEN $fact_id ELSE dup.id END AS fact_id,
       dup.id AS duplicate_of,
       [x IN closing | x.id] AS superseded,
       [x IN clashing | x.id] AS contradicts
