// name: staleness/mark_changed
// purpose: ONE atomic statement for a batch of code changes (at most 200 entries): find which anchors / doc Sources really changed (hash differs), make the active and dormant Facts that depend on them suspect, record one Change with TOUCHED / SUSPECTED edges, and report the decisions at risk and the docs to update.
// params: changes:list[map], paths:list[str], change_id:str, commit:str, at:int, now:int, agent_id:str, limit:int, limit_plus:int, max_detail:int
// returns: one row: change_id (null when nothing changed), changed (entries whose hash changed), fact_ids (active facts made suspect by THIS call; at most limit), decisions ([{id, text}], at most max_detail), decisions_total, docs ([{source_id, uri, anchor}]), truncated (true when more than `limit` facts are affected: call again with the same arguments to continue).
// mode: rw
// Each entry of $changes: {anchor_id, path, symbol, kind ('file'|'function'|'class'), repo, new_hash, old_hash, cover}. `cover` is true on a file-level entry whose file has no symbol entries in the batch: then a file change also covers that file's symbol anchors.
// Changed = previous hash <> '' and <> new_hash, where previous is the hash stored on the anchor (or the Source's content_hash) or, when none, the caller's old_hash. A first sighting without old_hash is a baseline and marks nothing. new_hash = '' means the file / symbol is gone.
// Affected facts: status 'active' or 'dormant' (a swept fact must be doubted too, or restore_fact would bring it back looking fresh; fact_ids lists the active ones only) that are ANCHORED_TO a changed anchor or reach a Source whose uri is a changed file through DERIVED_FROM*1..5, expanded level by level (D-014).
// Truncation: at most $limit facts per call ($limit_plus = $limit + 1 detects truncation; LIMIT takes no expression). When more are affected the hashes are NOT advanced and the Change id is deterministic, so the same call again continues (facts already SUSPECTED by that Change are skipped; the hashes advance on the last call).
// 6.0.2: a WHERE on an OPTIONAL MATCH after aggregations evaluated false for an existing node, so the doc filter is a CASE in the next WITH. Writes stay bounded (<= 200 entries, <= $limit facts).
UNWIND $changes AS c
OPTIONAL MATCH (a:CodeAnchor {id: c.anchor_id})
OPTIONAL MATCH (s:Source {uri: c.path}) WHERE c.kind = 'file'
WITH c, a, s,
     CASE WHEN a IS NULL OR coalesce(a.hash, '') = '' THEN c.old_hash ELSE a.hash END AS pa,
     CASE WHEN s IS NULL OR coalesce(s.content_hash, '') = '' THEN c.old_hash ELSE s.content_hash END AS ps
WITH c, a, s, (pa <> '' AND pa <> c.new_hash) AS ach, (s IS NOT NULL AND ps <> '' AND ps <> c.new_hash) AS sch
WITH collect(CASE WHEN ach OR sch THEN c END) AS cc,
     collect(CASE WHEN ach AND a IS NOT NULL THEN a END) AS cas,
     collect(CASE WHEN s IS NOT NULL AND (ach OR sch) THEN s END) AS srcs,
     collect(s) AS srcs_all
WITH cc, cas, srcs, srcs_all, [x IN cc WHERE x.kind = 'file' AND x.cover | x.path] AS cpaths
UNWIND CASE WHEN size(cpaths) = 0 THEN [null] ELSE cpaths END AS cp
OPTIONAL MATCH (sa:CodeAnchor {path: cp}) WHERE sa.symbol <> ''
WITH cc, cas, srcs, srcs_all, collect(sa) AS sas
WITH cc, srcs, srcs_all, cas + sas AS aff
UNWIND CASE WHEN size(aff) = 0 THEN [null] ELSE aff END AS ax
OPTIONAL MATCH (fa:Fact)-[:ANCHORED_TO]->(ax)
WITH cc, srcs, srcs_all, aff, collect(DISTINCT fa) AS fa_list
UNWIND CASE WHEN size(srcs) = 0 THEN [null] ELSE srcs END AS sx
OPTIONAL MATCH (n1:Fact)-[:DERIVED_FROM]->(sx)
WITH cc, srcs, srcs_all, aff, fa_list, collect(DISTINCT n1) AS l1
UNWIND CASE WHEN size(l1) = 0 THEN [null] ELSE l1 END AS x1
OPTIONAL MATCH (n2:Fact)-[:DERIVED_FROM]->(x1)
WITH cc, srcs_all, aff, fa_list, l1, collect(DISTINCT n2) AS l2
UNWIND CASE WHEN size(l2) = 0 THEN [null] ELSE l2 END AS x2
OPTIONAL MATCH (n3:Fact)-[:DERIVED_FROM]->(x2)
WITH cc, srcs_all, aff, fa_list, l1, l2, collect(DISTINCT n3) AS l3
UNWIND CASE WHEN size(l3) = 0 THEN [null] ELSE l3 END AS x3
OPTIONAL MATCH (n4:Fact)-[:DERIVED_FROM]->(x3)
WITH cc, srcs_all, aff, fa_list, l1, l2, l3, collect(DISTINCT n4) AS l4
UNWIND CASE WHEN size(l4) = 0 THEN [null] ELSE l4 END AS x4
OPTIONAL MATCH (n5:Fact)-[:DERIVED_FROM]->(x4)
WITH cc, srcs_all, aff, fa_list, l1 + l2 + l3 + l4 AS reach4, collect(DISTINCT n5) AS l5
WITH cc, srcs_all, aff, [r IN fa_list + reach4 + l5 WHERE r.status IN ['active', 'dormant']] AS cand
UNWIND CASE WHEN size(cand) = 0 THEN [null] ELSE cand END AS f
OPTIONAL MATCH (:Change {id: $change_id})-[sr:SUSPECTED]->(f)
WITH cc, srcs_all, aff, f, sr
WHERE f IS NULL OR sr IS NULL
WITH DISTINCT cc, srcs_all, aff, f LIMIT $limit_plus
WITH cc, srcs_all, aff, collect(f) AS fs_all
WITH cc, srcs_all, aff, fs_all[0..$limit] AS fs, size(fs_all) > $limit AS truncated
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS fx
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(fx)
WITH cc, srcs_all, aff, fs, truncated, collect(DISTINCT d) AS ds
UNWIND CASE WHEN size(aff) = 0 THEN [null] ELSE aff END AS ay
OPTIONAL MATCH (ds0:Source)-[:DESCRIBES]->(ay)
WITH cc, srcs_all, aff, fs, truncated, ds, ay,
     CASE WHEN ds0 IS NOT NULL AND NOT (ds0.uri IN $paths) THEN ds0 END AS dsk
WITH cc, srcs_all, aff, fs, truncated, ds,
     collect(DISTINCT CASE WHEN dsk IS NULL THEN null ELSE
       {source_id: dsk.id, uri: dsk.uri, anchor: ay.path + CASE WHEN ay.symbol = '' THEN '' ELSE '#' + ay.symbol END} END) AS docs
WITH cc, srcs_all, aff, fs, truncated, ds, docs, size(cc) > 0 AS anychanged,
     [x IN cc | x.anchor_id] AS ccids
FOREACH (z IN fs |
  SET z.suspect_since = CASE WHEN coalesce(z.verify_state, 'verified') = 'suspect' AND coalesce(z.suspect_since, 0) > 0
                             THEN z.suspect_since ELSE $at END,
      z.verify_state = 'suspect')
FOREACH (c IN CASE WHEN anychanged THEN [] ELSE $changes END |
  MERGE (an:CodeAnchor {id: c.anchor_id})
    ON CREATE SET an.repo = c.repo, an.path = c.path, an.symbol = c.symbol, an.kind = c.kind, an.hash = c.new_hash,
      an.updated_at = $at, an.created_at = $now
    ON MATCH SET an.updated_at = CASE WHEN an.hash = c.new_hash THEN an.updated_at ELSE $at END, an.hash = c.new_hash)
FOREACH (x IN CASE WHEN truncated THEN [] ELSE srcs_all END |
  SET x.content_hash = head([k IN $changes WHERE k.path = x.uri AND k.kind = 'file' | k.new_hash]),
      x.commit = CASE WHEN $commit = '' THEN coalesce(x.commit, '') ELSE $commit END)
FOREACH (_ IN CASE WHEN anychanged THEN [1] ELSE [] END |
  MERGE (ch:Change {id: $change_id})
    ON CREATE SET ch.commit = $commit, ch.at = $at, ch.paths = toJSON([k IN cc | k.path]), ch.agent_id = $agent_id,
      ch.created_at = $now
  FOREACH (z IN fs | MERGE (ch)-[r:SUSPECTED]->(z) ON CREATE SET r.at = $at)
  FOREACH (an IN aff | MERGE (ch)-[:TOUCHED]->(an))
  FOREACH (x IN srcs_all | FOREACH (_t IN CASE WHEN x.uri IN [k IN cc | k.path] THEN [1] ELSE [] END | MERGE (ch)-[:TOUCHED]->(x)))
  FOREACH (c IN CASE WHEN truncated THEN [] ELSE $changes END |
    MERGE (an:CodeAnchor {id: c.anchor_id})
      ON CREATE SET an.repo = c.repo, an.path = c.path, an.symbol = c.symbol, an.kind = c.kind, an.hash = c.new_hash,
        an.updated_at = $at, an.created_at = $now
      ON MATCH SET an.updated_at = CASE WHEN an.hash = c.new_hash THEN an.updated_at ELSE $at END, an.hash = c.new_hash
    FOREACH (_a IN CASE WHEN c.anchor_id IN ccids THEN [1] ELSE [] END | MERGE (ch)-[:TOUCHED]->(an))))
RETURN CASE WHEN anychanged THEN $change_id ELSE null END AS change_id, size(cc) AS changed,
       [z IN fs WHERE z.status = 'active' | z.id] AS fact_ids,
       [e IN ds[0..$max_detail] | {id: e.id, text: e.text}] AS decisions, size(ds) AS decisions_total, docs, truncated
