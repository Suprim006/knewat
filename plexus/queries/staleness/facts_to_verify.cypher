// name: staleness/facts_to_verify
// purpose: Enrich suspect fact ids for an agent to re-check: what the fact says, why it is suspect (newest Change that SUSPECTED it), the non-flagged Decisions built on it and the code / files it depends on; ordered by impact.
// params: ids:list[str], scope_id:str, open_to:int, limit:int
// returns: fact_id, entity, predicate, value, scope_id, verify_state, suspect_since, verify_after, decisions_count (non-flagged BASED_ON), anchors (path#symbol of ANCHORED_TO anchors, then the uri of directly DERIVED_FROM Sources), change_id, change_commit, change_at, change_paths (JSON list; null when no Change suspected it). Ordered by decisions_count DESC, then suspect_since ASC, then fact_id.
// mode: ro
// $scope_id = '' means every scope; otherwise the fact must be in that scope or one it INHERITS (up to 3 hops, as recall does). suspect_since is the Change time for a suspect fact and the review date for a fact that is only due.
// Plan shape (P7-07): the id seek comes first (`MATCH (f:Fact {id: fid})` alone, then a WITH, then the traversal). Written as one pattern with the ABOUT edge the planner traversed from EVERY fact and filtered by id afterwards, O(ids x facts); tests/integration/test_p7_plans.py pins the index seek.
// Activation ordering (D-012) is applied by the Python layer after this query (Staleness(rank=...)).
UNWIND $ids AS fid
MATCH (f:Fact {id: fid})
WITH f
MATCH (f)-[:ABOUT]->(e:Entity)
MATCH (f)-[:IN_SCOPE]->(sc:Scope)
WITH f, e, sc
WHERE $scope_id = '' OR (:Scope {id: $scope_id})-[:INHERITS*0..3]->(sc)
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(f)
WITH f, e, sc, count(CASE WHEN d IS NOT NULL AND NOT coalesce(d.flagged, false) THEN 1 END) AS dc
OPTIONAL MATCH (ch:Change)-[:SUSPECTED]->(f)
WITH f, e, sc, dc, ch ORDER BY ch.at DESC
WITH f, e, sc, dc, collect(ch)[0] AS last
WITH f, e, sc, dc, last,
     CASE WHEN coalesce(f.verify_state, 'verified') = 'suspect' AND coalesce(f.suspect_since, 0) > 0 THEN f.suspect_since
          ELSE coalesce(f.verify_after, $open_to) END AS since
RETURN f.id AS fact_id, e.name AS entity, f.predicate AS predicate, f.value AS value, sc.id AS scope_id,
       coalesce(f.verify_state, 'verified') AS verify_state, since AS suspect_since,
       coalesce(f.verify_after, $open_to) AS verify_after, dc AS decisions_count,
       [(f)-[:ANCHORED_TO]->(a:CodeAnchor) | a.path + CASE WHEN a.symbol = '' THEN '' ELSE '#' + a.symbol END]
         + [(f)-[:DERIVED_FROM]->(s:Source) | s.uri] AS anchors,
       last.id AS change_id, last.commit AS change_commit, last.at AS change_at, last.paths AS change_paths
ORDER BY dc DESC, since ASC, f.id ASC
LIMIT $limit
