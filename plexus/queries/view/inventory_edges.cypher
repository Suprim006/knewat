// name: view/inventory_edges
// purpose: Edge count per relationship type (the View's data inventory), one O(1) count per graph-model type; types with no edges are omitted.
// params: none
// returns: type, n (sorted by type)
// mode: ro
// Same idea as view/inventory_nodes: the type list is the graph model's, the API falls back to view/inventory_edges_scan for any type not listed here.
MATCH ()-[r:ABOUT]->() WITH count(r) AS n WHERE n > 0 RETURN 'ABOUT' AS type, n
UNION ALL
MATCH ()-[r:ANCHORED_TO]->() WITH count(r) AS n WHERE n > 0 RETURN 'ANCHORED_TO' AS type, n
UNION ALL
MATCH ()-[r:ASSERTED_BY]->() WITH count(r) AS n WHERE n > 0 RETURN 'ASSERTED_BY' AS type, n
UNION ALL
MATCH ()-[r:BASED_ON]->() WITH count(r) AS n WHERE n > 0 RETURN 'BASED_ON' AS type, n
UNION ALL
MATCH ()-[r:BY]->() WITH count(r) AS n WHERE n > 0 RETURN 'BY' AS type, n
UNION ALL
MATCH ()-[r:CARRIES]->() WITH count(r) AS n WHERE n > 0 RETURN 'CARRIES' AS type, n
UNION ALL
MATCH ()-[r:CLAIMED]->() WITH count(r) AS n WHERE n > 0 RETURN 'CLAIMED' AS type, n
UNION ALL
MATCH ()-[r:CONTRADICTS]->() WITH count(r) AS n WHERE n > 0 RETURN 'CONTRADICTS' AS type, n
UNION ALL
MATCH ()-[r:CREATED]->() WITH count(r) AS n WHERE n > 0 RETURN 'CREATED' AS type, n
UNION ALL
MATCH ()-[r:DECIDED]->() WITH count(r) AS n WHERE n > 0 RETURN 'DECIDED' AS type, n
UNION ALL
MATCH ()-[r:DEPENDS_ON]->() WITH count(r) AS n WHERE n > 0 RETURN 'DEPENDS_ON' AS type, n
UNION ALL
MATCH ()-[r:DERIVED_FROM]->() WITH count(r) AS n WHERE n > 0 RETURN 'DERIVED_FROM' AS type, n
UNION ALL
MATCH ()-[r:DESCRIBES]->() WITH count(r) AS n WHERE n > 0 RETURN 'DESCRIBES' AS type, n
UNION ALL
MATCH ()-[r:DUPLICATES]->() WITH count(r) AS n WHERE n > 0 RETURN 'DUPLICATES' AS type, n
UNION ALL
MATCH ()-[r:FOR]->() WITH count(r) AS n WHERE n > 0 RETURN 'FOR' AS type, n
UNION ALL
MATCH ()-[r:FROM]->() WITH count(r) AS n WHERE n > 0 RETURN 'FROM' AS type, n
UNION ALL
MATCH ()-[r:HAD]->() WITH count(r) AS n WHERE n > 0 RETURN 'HAD' AS type, n
UNION ALL
MATCH ()-[r:HAS_EPISODE]->() WITH count(r) AS n WHERE n > 0 RETURN 'HAS_EPISODE' AS type, n
UNION ALL
MATCH ()-[r:INHERITS]->() WITH count(r) AS n WHERE n > 0 RETURN 'INHERITS' AS type, n
UNION ALL
MATCH ()-[r:IN_SCOPE]->() WITH count(r) AS n WHERE n > 0 RETURN 'IN_SCOPE' AS type, n
UNION ALL
MATCH ()-[r:IN_STEP]->() WITH count(r) AS n WHERE n > 0 RETURN 'IN_STEP' AS type, n
UNION ALL
MATCH ()-[r:NEXT]->() WITH count(r) AS n WHERE n > 0 RETURN 'NEXT' AS type, n
UNION ALL
MATCH ()-[r:PRODUCED_BY]->() WITH count(r) AS n WHERE n > 0 RETURN 'PRODUCED_BY' AS type, n
UNION ALL
MATCH ()-[r:READ]->() WITH count(r) AS n WHERE n > 0 RETURN 'READ' AS type, n
UNION ALL
MATCH ()-[r:RELATES]->() WITH count(r) AS n WHERE n > 0 RETURN 'RELATES' AS type, n
UNION ALL
MATCH ()-[r:RETURNED]->() WITH count(r) AS n WHERE n > 0 RETURN 'RETURNED' AS type, n
UNION ALL
MATCH ()-[r:SUPERSEDES]->() WITH count(r) AS n WHERE n > 0 RETURN 'SUPERSEDES' AS type, n
UNION ALL
MATCH ()-[r:SUSPECTED]->() WITH count(r) AS n WHERE n > 0 RETURN 'SUSPECTED' AS type, n
UNION ALL
MATCH ()-[r:TO]->() WITH count(r) AS n WHERE n > 0 RETURN 'TO' AS type, n
UNION ALL
MATCH ()-[r:TOUCHED]->() WITH count(r) AS n WHERE n > 0 RETURN 'TOUCHED' AS type, n
UNION ALL
MATCH ()-[r:UPDATED]->() WITH count(r) AS n WHERE n > 0 RETURN 'UPDATED' AS type, n
UNION ALL
MATCH ()-[r:USED_IN]->() WITH count(r) AS n WHERE n > 0 RETURN 'USED_IN' AS type, n
UNION ALL
MATCH ()-[r:VERIFIED_BY]->() WITH count(r) AS n WHERE n > 0 RETURN 'VERIFIED_BY' AS type, n
UNION ALL
MATCH ()-[r:WROTE]->() WITH count(r) AS n WHERE n > 0 RETURN 'WROTE' AS type, n
