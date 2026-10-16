// name: engram/assert_fact
// purpose: ONE atomic statement: classify the new assertion against the current facts of the same entity+predicate+scope (duplicate / supersede / contradiction), then write it with provenance.
// params: entity_id:str, predicate:str, value:str, norm_value:str, value_tokens:str, dup_key:str, tok:list[str], tok_seq:list[str], scope_id:str, agent_id:str,
//   source_id:str, episode_id:str, step_id:str ('' = none), confidence:float, supersede:bool, now:int, open_to:int,
//   fact_id:str, emb:list[float], value_emb:list[float], dup_threshold:float, jac2:float, cos2:float, maybe_cos:float, maybe_jac:float, maybe_cap:int,
//   novelty:float, surprise_supersede:float, surprise_contradict:float
// returns: fact_id (the new fact, or the existing duplicate), duplicate_of (id or null), superseded (ids), contradicts (ids), surprise (the Fact.surprise stored on the NEW fact; null for a duplicate, which stores nothing), maybe (the soft duplicates the new fact was linked to: [{id, value, cos, jac}], nearest first; [] for a duplicate); no row when the entity, scope, or a given episode/source does not exist (nothing is written, not even the Agent)
// mode: rw

// Rules, evaluated on facts with status 'active' or 'dormant' and valid_to=open_to in the same scope (P7-02: a fact a sweep moved to
// 'dormant' is still the current value of its entity+predicate, so a new value closes or contradicts it like any other; a duplicate
// of a dormant fact wakes it instead of creating a twin: status = prior_status, prior_status / dormant_at removed):
//   dup        = first current fact (tiers in this order) with
//                  0. the same norm_value; else, among facts with the SAME dup_key (the discriminator multiset of dedup.py: numbers,
//                  unit-normalised quantities, number words, negation / antonym tokens; 'v1.2.3' != 'v1.2.4', 'enabled' != 'not enabled',
//                  '5 minutes' == '300 s' != '5 hours') and not the same-words-other-order case (tok equal but tok_seq different):
//                  1. value_emb within dup_threshold (cosine distance); a negative dup_threshold switches tiers 1 and 2 off;
//                  2. token Jaccard of tok >= jac2 AND value_emb within cos2 (B1).
//                Blocked (never tiers 1/2): same content words in another order, and a pure one-word substitution (one content token
//                on each side, or the same-length token sequences differ in one position: 'on Monday' / 'on Tuesday', 'server error' /
//                'client error' in a sentence that also says 'client').
//                Facts written before P9-c have no dup_key: they only match by norm_value (a missed merge, never a wrong one).
//   soft       = (no dup) current facts with the same dup_key and (cosine <= maybe_cos or Jaccard >= maybe_jac), nearest first, at most
//                maybe_cap: the new fact is created AND linked (new)-[:DUPLICATES_MAYBE {score, cos, jaccard, at}]->(old) (B2).
//   dup found  -> no new Fact (a single fact is kept, there is no DUPLICATES edge);
//                 MERGE (dup)-[:ASSERTED_BY {at: now, text: <raw value>}]->agent (+ DERIVED_FROM episode/source). The edge keeps its first
//                 `at` and `text`; `text` is the wording this agent used, so a wrong merge is detectable and reversible (B0).
//   closing    = current facts other than dup that were asserted only by this agent, or all of them when supersede=true.
//                On the dup path this agent endorses the dup instead of its own earlier, different belief (A/B/A, P1-03):
//                closing get valid_to=ts, status='superseded' + (dup)-[:SUPERSEDES]->(old).
//   ts         = max(now, valid_from of every closing fact): the effective time of the change. Racing writers whose clocks
//                disagree by a few ms would otherwise close a fact BEFORE it opened (valid_to < valid_from); with ts the chain
//                of windows stays contiguous and non-negative. ASSERTED_BY.at / recorded_at keep the caller's `now`.
//   otherwise  -> clashing  = the remaining current facts (other agents' view)
//                 new Fact (valid_from=ts); closing get valid_to=ts,status='superseded' + (new)-[:SUPERSEDES]->(old); clashing get (new)-[:CONTRADICTS]->(old) and stay active
// step_id (P9-int): the Step the runtime opened before this call ('' = none). A NEW fact is linked (Step)-[:WROTE]->(fact) in this same
// statement, so a crash cannot leave a fact without its WROTE edge (L6-F). A duplicate writes no fact and no WROTE.
// Plan shape (P5 review Q2): the current-fact lookup is anchored at the Entity (its ABOUT edges, then the predicate / status / valid_to
// filters, then the scope test via Expand Into). With `Fact {subject_id: ...}-[:IN_SCOPE]->(sc)` the planner started at the bound Scope
// and enumerated every fact of it, so the write-serialised assert path cost O(facts in the scope). subject_id always equals the ABOUT
// entity's id (this query is the only writer of Facts), so the edge is equivalent.
// FalkorDB 6.0.2 gotcha: two CASE-wrapped list comprehensions with a nested pattern comprehension in ONE WITH return wrong (empty/duplicated) lists,
// so closing and clashing are projected in separate WITH clauses.
// Surprise (D-012), stored once on the new Fact: contradicting another agent's current fact = $surprise_contradict (0.9); closing (superseding) a current
// fact = $surprise_supersede (0.6); otherwise $novelty (the caller's single vector read, activation/novelty: min(0.5, max(0, 1 - max cosine)), 0.5 for the
// first fact of a scope). It is decided here because only this statement knows whether the write supersedes or contradicts.
// source_id / episode_id are '' when absent. A given id that does not resolve yields no row (the guard sits before the Agent MERGE).
// Lineage tail: everything that follows the FOREACH is a plain RETURN; to log a Step, put `MATCH (st:Step {id: $step_id})` before the
//   FOREACHes and add `CREATE (st)-[:WROTE]->(nf)` inside the new-fact FOREACH (and `(st)-[:READ]->(x)` for dup/closing), then keep the RETURN.
MATCH (e:Entity {id: $entity_id}), (sc:Scope {id: $scope_id})
OPTIONAL MATCH (ep:Episode {id: $episode_id})
OPTIONAL MATCH (src:Source {id: $source_id})
OPTIONAL MATCH (stp:Step {id: $step_id})
OPTIONAL MATCH (e)<-[:ABOUT]-(f:Fact {predicate: $predicate, valid_to: $open_to})-[:IN_SCOPE]->(sc)
WHERE f.status IN ['active', 'dormant']
WITH e, sc, ep, src, stp, collect(f) AS cur
WHERE ($episode_id = '' OR ep IS NOT NULL) AND ($source_id = '' OR src IS NOT NULL)
MERGE (ag:Agent {id: $agent_id})
  ON CREATE SET ag.name = $agent_id, ag.created_at = $now
WITH ag, e, sc, ep, src, stp, cur,
     [xk IN cur WHERE xk.dup_key = $dup_key
      | {n: xk, cos: vec.cosineDistance(xk.value_embedding, vecf32($value_emb)),
         inter: size([kt IN $tok WHERE kt IN xk.tok]), nt: size(xk.tok)}] AS keyed0
WITH ag, e, sc, ep, src, stp, cur,
     [xk IN keyed0
      | {n: xk.n, cos: xk.cos,
         jac: CASE WHEN size($tok) + xk.nt = 0 THEN 0.0 ELSE toFloat(xk.inter) / (size($tok) + xk.nt - xk.inter) END,
         blocked: (xk.n.tok = $tok AND xk.n.tok_seq <> $tok_seq)
                  OR (size($tok) - xk.inter = 1 AND xk.nt - xk.inter = 1)
                  OR (size(xk.n.tok_seq) = size($tok_seq)
                      AND size([qi IN range(0, size($tok_seq) - 1) WHERE xk.n.tok_seq[qi] <> $tok_seq[qi]]) = 1)}] AS keyed
WITH ag, e, sc, ep, src, stp, cur, keyed,
     head([xe IN cur WHERE xe.norm_value = $norm_value]
          + [xn IN keyed WHERE NOT xn.blocked AND xn.cos <= $dup_threshold | xn.n]
          + [xj IN keyed WHERE NOT xj.blocked AND $dup_threshold >= 0 AND xj.jac >= $jac2 AND xj.cos <= $cos2 | xj.n]) AS dup
WITH ag, e, sc, ep, src, stp, cur, dup, keyed,
     [xc IN cur WHERE (dup IS NULL OR xc.id <> dup.id)
                      AND ($supersede OR all(ac IN [(xc)-[:ASSERTED_BY]->(oc:Agent) | oc.id] WHERE ac = $agent_id))] AS closing
WITH ag, e, sc, ep, src, stp, cur, dup, closing,
     CASE WHEN dup IS NULL AND $maybe_cap > 0 THEN
       [sx IN keyed WHERE sx.cos <= $maybe_cos OR sx.jac >= $maybe_jac][0..$maybe_cap]
     ELSE [] END AS soft
WITH ag, e, sc, ep, src, stp, cur, dup, closing, soft,
     reduce(m = $now, xt IN closing | CASE WHEN xt.valid_from > m THEN xt.valid_from ELSE m END) AS ts
WITH ag, e, sc, ep, src, stp, dup, closing, soft, ts,
     CASE WHEN dup IS NULL THEN
       [xk IN cur WHERE NOT ($supersede OR all(ak IN [(xk)-[:ASSERTED_BY]->(ok:Agent) | ok.id] WHERE ak = $agent_id))]
     ELSE [] END AS clashing
WITH ag, e, sc, ep, src, stp, dup, closing, soft, ts, clashing,
     CASE WHEN size(clashing) > 0 THEN $surprise_contradict
          WHEN size(closing) > 0 THEN $surprise_supersede
          ELSE $novelty END AS sp
FOREACH (d IN CASE WHEN dup IS NULL THEN [] ELSE [dup] END |
  MERGE (d)-[da:ASSERTED_BY]->(ag)
    ON CREATE SET da.at = $now, da.text = $value
  FOREACH (dw IN CASE WHEN d.status = 'dormant' THEN [d] ELSE [] END |
    SET dw.status = coalesce(dw.prior_status, 'active')
    REMOVE dw.prior_status, dw.dormant_at)
  FOREACH (de IN CASE WHEN ep IS NULL THEN [] ELSE [ep] END | MERGE (d)-[:DERIVED_FROM]->(de))
  FOREACH (ds IN CASE WHEN src IS NULL THEN [] ELSE [src] END | MERGE (d)-[:DERIVED_FROM]->(ds))
  FOREACH (c IN closing | SET c.valid_to = ts, c.status = 'superseded' MERGE (d)-[:SUPERSEDES]->(c)))
FOREACH (_ IN CASE WHEN dup IS NULL THEN [1] ELSE [] END |
  CREATE (nf:Fact {id: $fact_id, subject_id: $entity_id, predicate: $predicate, value: $value, norm_value: $norm_value,
                   value_tokens: $value_tokens, dup_key: $dup_key, tok: $tok, tok_seq: $tok_seq,
                   valid_from: ts, valid_to: $open_to, recorded_at: $now, created_at: $now,
                   status: 'active', confidence: $confidence, surprise: sp, embedding: vecf32($emb), value_embedding: vecf32($value_emb)})
  CREATE (nf)-[:ABOUT]->(e)
  CREATE (nf)-[:IN_SCOPE]->(sc)
  CREATE (nf)-[:ASSERTED_BY {at: $now}]->(ag)
  FOREACH (sw IN CASE WHEN stp IS NULL THEN [] ELSE [stp] END | CREATE (sw)-[:WROTE]->(nf))
  FOREACH (ne IN CASE WHEN ep IS NULL THEN [] ELSE [ep] END | CREATE (nf)-[:DERIVED_FROM]->(ne))
  FOREACH (ns IN CASE WHEN src IS NULL THEN [] ELSE [src] END | CREATE (nf)-[:DERIVED_FROM]->(ns))
  FOREACH (c IN closing | SET c.valid_to = ts, c.status = 'superseded' CREATE (nf)-[:SUPERSEDES]->(c))
  FOREACH (c IN clashing | CREATE (nf)-[:CONTRADICTS]->(c))
  FOREACH (sm IN soft | FOREACH (so IN [sm.n] |
    CREATE (nf)-[:DUPLICATES_MAYBE {score: 1.0 - sm.cos, cos: sm.cos, jaccard: sm.jac, at: $now}]->(so))))
RETURN CASE WHEN dup IS NULL THEN $fact_id ELSE dup.id END AS fact_id,
       dup.id AS duplicate_of,
       [rc IN closing | rc.id] AS superseded,
       [rk IN clashing | rk.id] AS contradicts,
       CASE WHEN dup IS NULL THEN sp ELSE null END AS surprise,
       [sr IN soft | {id: sr.n.id, value: sr.n.value, cos: sr.cos, jac: sr.jac}] AS maybe
