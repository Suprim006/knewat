// name: engram/count_missing_search_text
// purpose: How many facts (with an ABOUT entity) have no Fact.search_text yet (written before P12); the dry run of engram/backfill_search_text.
// params: none
// returns: n
// mode: ro
MATCH (f:Fact)-[:ABOUT]->(:Entity)
WHERE f.search_text IS NULL
RETURN count(f) AS n
