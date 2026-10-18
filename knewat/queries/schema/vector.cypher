// name: schema/vector
// purpose: Vector indexes (384-d, cosine; bge-small embeddings) on Entity, Fact and Episode for semantic seeding of recall.
// params: none
// returns: nothing (one CREATE VECTOR INDEX per statement; re-running errors with "already indexed", which apply_schema tolerates)
// mode: rw
// split: ;
// 6.0.2: the cosine score is a distance (identical vector ~ 0), so rank nearest-first with ORDER BY score ASC.
CREATE VECTOR INDEX FOR (n:Entity) ON (n.embedding) OPTIONS {dimension: 384, similarityFunction: 'cosine'};
CREATE VECTOR INDEX FOR (n:Fact) ON (n.embedding) OPTIONS {dimension: 384, similarityFunction: 'cosine'};
CREATE VECTOR INDEX FOR (n:Episode) ON (n.embedding) OPTIONS {dimension: 384, similarityFunction: 'cosine'}
