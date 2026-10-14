// name: schema/fulltext
// purpose: Full-text indexes from graph model v1 (Entity.name, Fact.value, Episode.text) for keyword entity resolution and recall.
// params: none
// returns: nothing (one CREATE FULLTEXT INDEX per statement; re-running errors with "already indexed", which apply_schema tolerates)
// mode: rw
// split: ;
CREATE FULLTEXT INDEX FOR (n:Entity) ON (n.name);
CREATE FULLTEXT INDEX FOR (n:Fact) ON (n.value);
CREATE FULLTEXT INDEX FOR (n:Episode) ON (n.text)
