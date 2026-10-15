// name: staleness/docs_to_update
// purpose: Doc Sources that DESCRIBE code which changed after $since and which have not been edited since (no later TOUCHED of the doc itself), newest change first.
// params: since:int, limit:int, per_doc:int
// returns: source_id, uri, title, latest (time of the newest relevant change), changes ([{change_id, commit, at, paths (JSON list), anchor}] newest first, at most per_doc)
// mode: ro
// A Change counts for a doc when it TOUCHED an anchor the doc DESCRIBES and ch.at > $since and ch.at > the doc's own last TOUCHED (a doc edited in the same commit as the code has an equal time and is not listed).
MATCH (ch:Change) WHERE ch.at > $since
MATCH (ch)-[:TOUCHED]->(a:CodeAnchor)<-[:DESCRIBES]-(d:Source)
OPTIONAL MATCH (dc:Change)-[:TOUCHED]->(d)
WITH ch, a, d, max(dc.at) AS doc_at
WITH ch, a, d, CASE WHEN doc_at IS NULL OR ch.at > doc_at THEN true ELSE false END AS fresh
WITH ch, a, d WHERE fresh
WITH d, ch, a ORDER BY ch.at DESC
WITH d, collect({change_id: ch.id, commit: ch.commit, at: ch.at, paths: ch.paths,
                 anchor: a.path + CASE WHEN a.symbol = '' THEN '' ELSE '#' + a.symbol END}) AS items
WITH d, items, items[0].at AS latest
RETURN d.id AS source_id, d.uri AS uri, coalesce(d.title, '') AS title, latest, items[0..$per_doc] AS changes
ORDER BY latest DESC, d.id ASC
LIMIT $limit
