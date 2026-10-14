// name: engram/assert_fact
// purpose: ONE atomic statement: classify the new assertion against the current facts of the same entity+predicate+scope (duplicate / supersede / contradiction), then write it with provenance.
// params: entity_id:str, predicate:str, value:str, norm_value:str, value_tokens:str, scope_id:str, agent_id:str,
//   source_id:str, episode_id:str, confidence:float, supersede:bool, now:int, open_to:int,
//   fact_id:str, emb:list[float], value_emb:list[float], dup_threshold:float
// returns: fact_id (the new fact, or the existing duplicate), duplicate_of (id or null), superseded (ids), contradicts (ids); no row when the entity, scope, or a given episode/source does not exist (nothing is written, not even the Agent)
// mode: rw

// Rules, evaluated on facts with status='active' and valid_to=open_to in the same scope:
//   dup        = first current fact with the same norm_value, else with value_tokens equal (the sorted multiset of
//                numeric/version tokens, e.g. '16' vs '15', 'v1' vs 'v2' differ) AND value_emb within dup_threshold
//                (cosine distance). Embeddings alone cannot tell 'v1.2.3' from 'v1.2.4' (P1-01), so the tokens must agree.
//   dup found  -> no new Fact (a single fact is kept, there is no DUPLICATES edge);
//                 MERGE (dup)-[:ASSERTED_BY {at: now}]->agent (+ DERIVED_FROM episode/source). The edge keeps its first `at`.
//   closing    = current facts other than dup that were asserted only by this agent, or all of them when supersede=true.
//                On the dup path this agent endorses the dup instead of its own earlier, different belief (A/B/A, P1-03):
//                closing get valid_to=now, status='superseded' + (dup)-[:SUPERSEDES]->(old).
//   otherwise  -> clashing  = the remaining current facts (other agents' view)
//                 new Fact; closing get valid_to=now,status='superseded' + (new)-[:SUPERSEDES]->(old); clashing get (new)-[:CONTRADICTS]->(old) and stay active
// FalkorDB 6.0.2 gotcha: two CASE-wrapped list comprehensions with a nested pattern comprehension in ONE WITH return wrong (empty/duplicated) lists,
// so closing and clashing are projected in separate WITH clauses.
// source_id / episode_id are '' when absent. A given id that does not resolve yields no row (the guard sits before the Agent MERGE).
// Lineage tail: everything that follows the FOREACH is a plain RETURN; to log a Step, put `MATCH (st:Step {id: $step_id})` before the
//   FOREACHes and add `CREATE (st)-[:WROTE]->(nf)` inside the new-fact FOREACH (and `(st)-[:READ]->(x)` for dup/closing), then keep the RETURN.
MATCH (e:Entity {id: $entity_id}), (sc:Scope {id: $scope_id})
OPTIONAL MATCH (ep:Episode {id: $episode_id})
OPTIONAL MATCH (src:Source {id: $source_id})
OPTIONAL MATCH (f:Fact {subject_id: $entity_id, predicate: $predicate, status: 'active', valid_to: $open_to})-[:IN_SCOPE]->(sc)
WITH e, sc, ep, src, collect(f) AS cur
WHERE ($episode_id = '' OR ep IS NOT NULL) AND ($source_id = '' OR src IS NOT NULL)
MERGE (ag:Agent {id: $agent_id})
  ON CREATE SET ag.name = $agent_id, ag.created_at = $now
WITH ag, e, sc, ep, src, cur,
     head([xe IN cur WHERE xe.norm_value = $norm_value]
          + [xn IN cur WHERE xn.value_tokens = $value_tokens
                             AND vec.cosineDistance(xn.value_embedding, vecf32($value_emb)) <= $dup_threshold]) AS dup
WITH ag, e, sc, ep, src, cur, dup,
     [xc IN cur WHERE (dup IS NULL OR xc.id <> dup.id)
                      AND ($supersede OR all(ac IN [(xc)-[:ASSERTED_BY]->(oc:Agent) | oc.id] WHERE ac = $agent_id))] AS closing
WITH ag, e, sc, ep, src, dup, closing,
     CASE WHEN dup IS NULL THEN
       [xk IN cur WHERE NOT ($supersede OR all(ak IN [(xk)-[:ASSERTED_BY]->(ok:Agent) | ok.id] WHERE ak = $agent_id))]
     ELSE [] END AS clashing
FOREACH (d IN CASE WHEN dup IS NULL THEN [] ELSE [dup] END |
  MERGE (d)-[da:ASSERTED_BY]->(ag)
    ON CREATE SET da.at = $now
  FOREACH (de IN CASE WHEN ep IS NULL THEN [] ELSE [ep] END | MERGE (d)-[:DERIVED_FROM]->(de))
  FOREACH (ds IN CASE WHEN src IS NULL THEN [] ELSE [src] END | MERGE (d)-[:DERIVED_FROM]->(ds))
  FOREACH (c IN closing | SET c.valid_to = $now, c.status = 'superseded' MERGE (d)-[:SUPERSEDES]->(c)))
FOREACH (_ IN CASE WHEN dup IS NULL THEN [1] ELSE [] END |
  CREATE (nf:Fact {id: $fact_id, subject_id: $entity_id, predicate: $predicate, value: $value, norm_value: $norm_value,
                   value_tokens: $value_tokens, valid_from: $now, valid_to: $open_to, recorded_at: $now, created_at: $now,
                   status: 'active', confidence: $confidence, embedding: vecf32($emb), value_embedding: vecf32($value_emb)})
  CREATE (nf)-[:ABOUT]->(e)
  CREATE (nf)-[:IN_SCOPE]->(sc)
  CREATE (nf)-[:ASSERTED_BY {at: $now}]->(ag)
  FOREACH (ne IN CASE WHEN ep IS NULL THEN [] ELSE [ep] END | CREATE (nf)-[:DERIVED_FROM]->(ne))
  FOREACH (ns IN CASE WHEN src IS NULL THEN [] ELSE [src] END | CREATE (nf)-[:DERIVED_FROM]->(ns))
  FOREACH (c IN closing | SET c.valid_to = $now, c.status = 'superseded' CREATE (nf)-[:SUPERSEDES]->(c))
  FOREACH (c IN clashing | CREATE (nf)-[:CONTRADICTS]->(c)))
RETURN CASE WHEN dup IS NULL THEN $fact_id ELSE dup.id END AS fact_id,
       dup.id AS duplicate_of,
       [rc IN closing | rc.id] AS superseded,
       [rk IN clashing | rk.id] AS contradicts
