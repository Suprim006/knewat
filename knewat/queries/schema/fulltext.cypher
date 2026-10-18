// name: schema/fulltext
// purpose: Full-text indexes (Entity.name, Fact.value, Episode.text) for keyword entity resolution and recall, plus Fact.search_text (entity name + predicate words, so recall's keyword channel matches subject and predicate, not only the value).
// params: none
// returns: nothing (one CREATE FULLTEXT INDEX per statement; re-running errors with "already indexed", which apply_schema tolerates).
// A second CREATE on the same label ADDS a field to that label's one full-text index (6.0.2), so an existing graph gains Fact.search_text on the next apply_schema; older facts match by value only until `knewat migrate` backfills it.
// mode: rw
// split: ;
CREATE FULLTEXT INDEX FOR (n:Entity) ON (n.name);
CREATE FULLTEXT INDEX FOR (n:Fact) ON (n.value);
CREATE FULLTEXT INDEX FOR (n:Episode) ON (n.text);
CREATE FULLTEXT INDEX FOR (n:Fact) ON (n.search_text)
