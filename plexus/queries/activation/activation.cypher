// name: activation/activation
// purpose: Gather, for up to 200 facts, the access events and protection inputs that the Python activation model (plexus.activation) turns into A(f) (D-012). Nothing is computed or written here.
// params: fact_ids:list[str], now:int, events:int
// returns: one row per existing fact id: id, status, created_at, surprise (0 when absent), pinned (false when absent), verify_state ('verified' when absent), suspect_since (0 when absent), verify_after (9999999999999 = OPEN when absent), reads [{k:'use'|'recall', t}] (newest `events` READ edges with t <= now), asserted_at [ms] (every ASSERTED_BY edge), decisions [{id, t, flagged}] (BASED_ON), handoffs [{id, t}] (CARRIES), verified_at [ms] (VERIFIED_BY), supersedes [ids] (outgoing SUPERSEDES, at most 3), contradicts [ids] (CONTRADICTS either way, at most 3), sources [{id, trust}] (Sources reached by DERIVED_FROM 1..3 hops)
// mode: ro

// Event sources (all edges Plexus already writes; docs/P7-contract.md gives the weights, which the model applies):
//   create f.created_at; re-assert = an ASSERTED_BY edge with at > created_at (another agent); decision = Decision.created_at; handoff = Handoff.created_at;
//   use / recall = (Step)-[READ {via, at}]->(f), an absent via counts as 'recall' and an absent at falls back to the Step's at; verified = VERIFIED_BY.at (P7-J writes it;
//   on 6.0.2 a pattern over a relationship type that does not exist yet simply matches nothing).
// The Python wrapper filters by `now`, drops the creating ASSERTED_BY, applies the protection rules (pinned; an unflagged decision; any handoff; SUPERSEDES / CONTRADICTS;
//   trust = 'high') and keeps the newest K events overall. The READ list is the only unbounded one, so it is cut to the newest $events here (ORDER BY ... then a slice per fact).
// FalkorDB 6.0.2 gotchas found while writing this (each one gave empty or failing lists, not an error message that names the cause):
//   - several pattern comprehensions in the SAME RETURN as an aggregation, or two comprehensions over the same relationship pattern (one for the event, one for the
//     protection), return [] for some of them; so every relationship type is read by exactly ONE comprehension, all of them in one WITH before the READ aggregation;
//   - a WHERE inside a pattern comprehension that mixes f.created_at and $now misbehaved the same way, so the comprehensions have no WHERE (the wrapper filters);
//   - `[x IN collected WHERE ...]` next to pattern comprehensions fails with 'Type mismatch: expected Map ... but was List'; collect() skips nulls, so none is needed;
//   - a WHERE on the OPTIONAL MATCH rows would also drop the fact's own row, so a READ in the future of $now is turned into null inside the CASE.
// A fact id that does not exist gives no row. Facts are looked up one id at a time (`{id: fid}` is an index seek).
UNWIND $fact_ids AS fid
MATCH (f:Fact {id: fid})
WITH f,
     [(f)-[a:ASSERTED_BY]->(:Agent) | a.at] AS asserted_at,
     [(d:Decision)-[:BASED_ON]->(f) | {id: d.id, t: d.created_at, flagged: coalesce(d.flagged, false)}] AS decisions,
     [(h:Handoff)-[:CARRIES]->(f) | {id: h.id, t: h.created_at}] AS handoffs,
     [(f)-[v:VERIFIED_BY]->(:Agent) | v.at] AS verified_at,
     [(f)-[:SUPERSEDES]->(o:Fact) | o.id][0..3] AS supersedes,
     [(f)-[:CONTRADICTS]-(p:Fact) | p.id][0..3] AS contradicts,
     [(f)-[:DERIVED_FROM*1..3]->(src:Source) | {id: src.id, trust: src.trust}] AS sources
OPTIONAL MATCH (s:Step)-[r:READ]->(f)
WITH f, asserted_at, decisions, handoffs, verified_at, supersedes, contradicts, sources,
     CASE WHEN coalesce(r.at, s.at) <= $now THEN coalesce(r.at, s.at) ELSE null END AS t,
     CASE WHEN r.via = 'use' THEN 'use' ELSE 'recall' END AS k
ORDER BY t DESC
WITH f, asserted_at, decisions, handoffs, verified_at, supersedes, contradicts, sources,
     collect(CASE WHEN t IS NULL THEN null ELSE {k: k, t: t} END)[0..$events] AS reads
RETURN f.id AS id, f.status AS status, f.created_at AS created_at,
       coalesce(f.surprise, 0.0) AS surprise,
       coalesce(f.pinned, false) AS pinned,
       coalesce(f.verify_state, 'verified') AS verify_state,
       coalesce(f.suspect_since, 0) AS suspect_since,
       coalesce(f.verify_after, 9999999999999) AS verify_after,
       reads, asserted_at, decisions, handoffs, verified_at, supersedes, contradicts, sources
