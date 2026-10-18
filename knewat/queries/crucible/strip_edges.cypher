// name: crucible/strip_edges
// purpose: ABLATION only (D-001): delete the relationship types the product's features rest on - DEPENDS_ON, BASED_ON, DERIVED_FROM and READ - in bounded batches, to measure which capabilities break without them.
// params: limit:int
// returns: nothing used; each of the four statements deletes at most `limit` edges of one type (stats.relationships_deleted tells how many). Call until all four delete 0.
// mode: rw
// split: ;
// Bounded writes: LIMIT is applied in a WITH before DELETE, so the delete never exceeds $limit edges per statement.
// Never run against a real tenant: Crucible only calls this on its own throwaway ablation tenant.
MATCH ()-[r:DEPENDS_ON]->() WITH r LIMIT $limit DELETE r;
MATCH ()-[r:BASED_ON]->() WITH r LIMIT $limit DELETE r;
MATCH ()-[r:DERIVED_FROM]->() WITH r LIMIT $limit DELETE r;
MATCH ()-[r:READ]->() WITH r LIMIT $limit DELETE r
