// name: engram/backfill_search_text
// purpose: Set Fact.search_text (entity name + predicate words; P12, the keyword channel of recall) on up to $batch facts written before P12. Run in a loop until n = 0 (knewat migrate).
// params: batch:int
// returns: n (facts updated in this batch)
// mode: rw
// Predicate words: '_', '.' and '-' become spaces (the Python writer, knewat.engram.service.search_text, splits on every non-word character;
// predicates are normalised identifiers, so the two agree in practice). Facts without an ABOUT entity are skipped (they cannot be
// selected again, so the loop ends).
MATCH (f:Fact)-[:ABOUT]->(e:Entity)
WHERE f.search_text IS NULL
WITH f, e LIMIT $batch
SET f.search_text = e.name + ' ' + replace(replace(replace(f.predicate, '_', ' '), '.', ' '), '-', ' ')
RETURN count(f) AS n
