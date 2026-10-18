// name: lineage/why_edges
// purpose: The whole provenance subgraph behind a Decision or a Fact in ONE read statement (one snapshot, D-014): a flat edge list with the display properties of both ends.
// params: id:str, limit:int, depth:int, derived_limit:int
// returns: s, sl, rel, t, tl, prio, lv, sp, tp. One row per distinct edge: stored direction s -[rel]-> t with node ids, labels and display properties (sp / tp, the maps lineage/node_info returns); prio orders rows for truncation (1 = closest to the root); lv is the DERIVED_FROM level of an ancestry row (0 otherwise). rel = 'SELF' carries the root itself (s = t = $id). No row = the id is not a Decision or a Fact.
// mode: ro
// One UNION, so one snapshot (a statement per hop tore under concurrent writes). Branches: the root's own props (SELF); decision (DECIDED, FOR, BASED_ON, WROTE and the writing Step's agent); per base fact (ASSERTED_BY, ABOUT, IN_SCOPE, SUPERSEDES / CONTRADICTS / DUPLICATES both ways, WROTE Steps, suspecting Changes, VERIFIED_BY agents); the DERIVED_FROM ancestry.
// Ancestry: expanded level by level over DISTINCT facts (12 fixed one-hop steps, each skipped once $depth is reached; carried lists are aggregated with head(collect(...)), never grouping keys), cut at $derived_limit, nearest level first. `*1..N` would enumerate paths. Every other branch is capped by $limit rows.
MATCH (rf:Fact {id: $id})
RETURN rf.id AS s, 'Fact' AS sl, 'SELF' AS rel, rf.id AS t, 'Fact' AS tl, 0 AS prio, 0 AS lv,
       {predicate: rf.predicate, value: rf.value, status: rf.status, valid_from: rf.valid_from, valid_to: rf.valid_to, recorded_at: rf.recorded_at, confidence: rf.confidence, subject_id: rf.subject_id, verify_state: coalesce(rf.verify_state, 'verified'), suspect_since: coalesce(rf.suspect_since, 0), surprise: coalesce(rf.surprise, 0.0), pinned: coalesce(rf.pinned, false)} AS sp,
       {predicate: rf.predicate, value: rf.value, status: rf.status, valid_from: rf.valid_from, valid_to: rf.valid_to, recorded_at: rf.recorded_at, confidence: rf.confidence, subject_id: rf.subject_id, verify_state: coalesce(rf.verify_state, 'verified'), suspect_since: coalesce(rf.suspect_since, 0), surprise: coalesce(rf.surprise, 0.0), pinned: coalesce(rf.pinned, false)} AS tp
UNION
MATCH (rd:Decision {id: $id})
RETURN rd.id AS s, 'Decision' AS sl, 'SELF' AS rel, rd.id AS t, 'Decision' AS tl, 0 AS prio, 0 AS lv,
       {text: rd.text, at: rd.at, flagged: coalesce(rd.flagged, false)} AS sp,
       {text: rd.text, at: rd.at, flagged: coalesce(rd.flagged, false)} AS tp
UNION
MATCH (a:Agent)-[:DECIDED]->(d:Decision {id: $id})
RETURN a.id AS s, 'Agent' AS sl, 'DECIDED' AS rel, d.id AS t, 'Decision' AS tl, 1 AS prio, 0 AS lv,
       {name: a.name, role: a.role, harness: a.harness} AS sp,
       {text: d.text, at: d.at, flagged: coalesce(d.flagged, false)} AS tp LIMIT $limit
UNION
MATCH (d:Decision {id: $id})-[:FOR]->(k:Task)
RETURN d.id AS s, 'Decision' AS sl, 'FOR' AS rel, k.id AS t, 'Task' AS tl, 1 AS prio, 0 AS lv,
       {text: d.text, at: d.at, flagged: coalesce(d.flagged, false)} AS sp,
       {title: k.title, status: k.status} AS tp LIMIT $limit
UNION
MATCH (d:Decision {id: $id})-[:BASED_ON]->(f:Fact)
RETURN d.id AS s, 'Decision' AS sl, 'BASED_ON' AS rel, f.id AS t, 'Fact' AS tl, 1 AS prio, 0 AS lv,
       {text: d.text, at: d.at, flagged: coalesce(d.flagged, false)} AS sp,
       {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)} AS tp LIMIT $limit
UNION
MATCH (st:Step)-[:WROTE]->(d:Decision {id: $id})
RETURN st.id AS s, 'Step' AS sl, 'WROTE' AS rel, d.id AS t, 'Decision' AS tl, 1 AS prio, 0 AS lv,
       {n: st.n, at: st.at, agent_id: st.agent_id} AS sp,
       {text: d.text, at: d.at, flagged: coalesce(d.flagged, false)} AS tp LIMIT $limit
UNION
MATCH (st:Step)-[:WROTE]->(:Decision {id: $id})
MATCH (st)-[:BY]->(a:Agent)
RETURN st.id AS s, 'Step' AS sl, 'BY' AS rel, a.id AS t, 'Agent' AS tl, 1 AS prio, 0 AS lv,
       {n: st.n, at: st.at, agent_id: st.agent_id} AS sp,
       {name: a.name, role: a.role, harness: a.harness} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:ASSERTED_BY]->(a:Agent)
RETURN f.id AS s, 'Fact' AS sl, 'ASSERTED_BY' AS rel, a.id AS t, 'Agent' AS tl, 2 AS prio, 0 AS lv,
       {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)} AS sp,
       {name: a.name, role: a.role, harness: a.harness} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:ABOUT]->(e:Entity)
RETURN f.id AS s, 'Fact' AS sl, 'ABOUT' AS rel, e.id AS t, 'Entity' AS tl, 5 AS prio, 0 AS lv,
       {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)} AS sp,
       {name: e.name, kind: e.kind} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:IN_SCOPE]->(sc:Scope)
RETURN f.id AS s, 'Fact' AS sl, 'IN_SCOPE' AS rel, sc.id AS t, 'Scope' AS tl, 6 AS prio, 0 AS lv,
       {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)} AS sp,
       {kind: sc.kind, name: sc.name} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[r:SUPERSEDES|CONTRADICTS|DUPLICATES]->(o:Fact)
RETURN f.id AS s, 'Fact' AS sl, type(r) AS rel, o.id AS t, 'Fact' AS tl, 3 AS prio, 0 AS lv,
       {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)} AS sp,
       {predicate: o.predicate, value: o.value, status: o.status, valid_from: o.valid_from, valid_to: o.valid_to, recorded_at: o.recorded_at, confidence: o.confidence, subject_id: o.subject_id, verify_state: coalesce(o.verify_state, 'verified'), suspect_since: coalesce(o.suspect_since, 0), surprise: coalesce(o.surprise, 0.0), pinned: coalesce(o.pinned, false)} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (o:Fact)-[r:SUPERSEDES|CONTRADICTS|DUPLICATES]->(f)
RETURN o.id AS s, 'Fact' AS sl, type(r) AS rel, f.id AS t, 'Fact' AS tl, 3 AS prio, 0 AS lv,
       {predicate: o.predicate, value: o.value, status: o.status, valid_from: o.valid_from, valid_to: o.valid_to, recorded_at: o.recorded_at, confidence: o.confidence, subject_id: o.subject_id, verify_state: coalesce(o.verify_state, 'verified'), suspect_since: coalesce(o.suspect_since, 0), surprise: coalesce(o.surprise, 0.0), pinned: coalesce(o.pinned, false)} AS sp,
       {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (st:Step)-[:WROTE]->(f)
RETURN st.id AS s, 'Step' AS sl, 'WROTE' AS rel, f.id AS t, 'Fact' AS tl, 2 AS prio, 0 AS lv,
       {n: st.n, at: st.at, agent_id: st.agent_id} AS sp,
       {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (st:Step)-[:WROTE]->(f)
MATCH (st)-[:BY]->(a:Agent)
RETURN st.id AS s, 'Step' AS sl, 'BY' AS rel, a.id AS t, 'Agent' AS tl, 2 AS prio, 0 AS lv,
       {n: st.n, at: st.at, agent_id: st.agent_id} AS sp,
       {name: a.name, role: a.role, harness: a.harness} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (ch:Change)-[:SUSPECTED]->(f)
RETURN ch.id AS s, 'Change' AS sl, 'SUSPECTED' AS rel, f.id AS t, 'Fact' AS tl, 2 AS prio, 0 AS lv,
       {commit: ch.commit, at: ch.at, paths: ch.paths, agent_id: ch.agent_id} AS sp,
       {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS base
UNWIND base AS f
MATCH (f)-[:VERIFIED_BY]->(a:Agent)
RETURN DISTINCT f.id AS s, 'Fact' AS sl, 'VERIFIED_BY' AS rel, a.id AS t, 'Agent' AS tl, 2 AS prio, 0 AS lv,
       {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)} AS sp,
       {name: a.name, role: a.role, harness: a.harness} AS tp LIMIT $limit
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(DISTINCT bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS fr
WITH fr, fr AS seen, [y IN fr | {f: y, lv: 1}] AS el
UNWIND CASE WHEN size(fr) = 0 OR $depth < 2 THEN [null] ELSE fr END AS a2
OPTIONAL MATCH (a2)-[:DERIVED_FROM]->(n2:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n2) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 2}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 3 THEN [null] ELSE fr END AS a3
OPTIONAL MATCH (a3)-[:DERIVED_FROM]->(n3:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n3) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 3}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 4 THEN [null] ELSE fr END AS a4
OPTIONAL MATCH (a4)-[:DERIVED_FROM]->(n4:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n4) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 4}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 5 THEN [null] ELSE fr END AS a5
OPTIONAL MATCH (a5)-[:DERIVED_FROM]->(n5:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n5) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 5}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 6 THEN [null] ELSE fr END AS a6
OPTIONAL MATCH (a6)-[:DERIVED_FROM]->(n6:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n6) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 6}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 7 THEN [null] ELSE fr END AS a7
OPTIONAL MATCH (a7)-[:DERIVED_FROM]->(n7:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n7) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 7}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 8 THEN [null] ELSE fr END AS a8
OPTIONAL MATCH (a8)-[:DERIVED_FROM]->(n8:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n8) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 8}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 9 THEN [null] ELSE fr END AS a9
OPTIONAL MATCH (a9)-[:DERIVED_FROM]->(n9:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n9) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 9}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 10 THEN [null] ELSE fr END AS a10
OPTIONAL MATCH (a10)-[:DERIVED_FROM]->(n10:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n10) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 10}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 11 THEN [null] ELSE fr END AS a11
OPTIONAL MATCH (a11)-[:DERIVED_FROM]->(n11:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n11) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 11}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 12 THEN [null] ELSE fr END AS a12
OPTIONAL MATCH (a12)-[:DERIVED_FROM]->(n12:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n12) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 12}] AS el, fr
UNWIND el AS e
WITH e.f AS f, e.lv AS lv
MATCH (f)-[:DERIVED_FROM]->(x)
WITH f, lv, x, labels(x)[0] AS xl
WITH f, lv, x, xl, [(x)-[:ASSERTED_BY]->(ga:Agent) | ga] AS gas
WITH f, lv, x, xl, gas, [(x)<-[:HAS_EPISODE]-(se:Session) | se] AS ses
UNWIND [{s: f.id, sl: 'Fact', rel: 'DERIVED_FROM', t: x.id, tl: xl, prio: 3, lv: lv,
         sp: {predicate: f.predicate, value: f.value, status: f.status, valid_from: f.valid_from, valid_to: f.valid_to, recorded_at: f.recorded_at, confidence: f.confidence, subject_id: f.subject_id, verify_state: coalesce(f.verify_state, 'verified'), suspect_since: coalesce(f.suspect_since, 0), surprise: coalesce(f.surprise, 0.0), pinned: coalesce(f.pinned, false)}, tp: CASE labels(x)[0] WHEN 'Fact' THEN {predicate: x.predicate, value: x.value, status: x.status, valid_from: x.valid_from, valid_to: x.valid_to, recorded_at: x.recorded_at, confidence: x.confidence, subject_id: x.subject_id, verify_state: coalesce(x.verify_state, 'verified'), suspect_since: coalesce(x.suspect_since, 0), surprise: coalesce(x.surprise, 0.0), pinned: coalesce(x.pinned, false)} WHEN 'Source' THEN {uri: x.uri, kind: x.kind, trust: x.trust} WHEN 'Episode' THEN {role: x.role, text: substring(x.text, 0, 200), at: x.at} ELSE {} END}]
       + [ga IN gas WHERE xl = 'Fact' | {s: x.id, sl: 'Fact', rel: 'ASSERTED_BY', t: ga.id, tl: 'Agent', prio: 4, lv: lv,
          sp: {predicate: x.predicate, value: x.value, status: x.status, valid_from: x.valid_from, valid_to: x.valid_to, recorded_at: x.recorded_at, confidence: x.confidence, subject_id: x.subject_id, verify_state: coalesce(x.verify_state, 'verified'), suspect_since: coalesce(x.suspect_since, 0), surprise: coalesce(x.surprise, 0.0), pinned: coalesce(x.pinned, false)}, tp: {name: ga.name, role: ga.role, harness: ga.harness}}]
       + [se IN ses WHERE xl = 'Episode' | {s: se.id, sl: 'Session', rel: 'HAS_EPISODE', t: x.id, tl: 'Episode', prio: 4, lv: lv,
          sp: {agent_id: se.agent_id, started_at: se.started_at}, tp: {role: x.role, text: substring(x.text, 0, 200), at: x.at}}]
       AS row
WITH DISTINCT row ORDER BY row.lv ASC, row.prio ASC, row.s ASC, row.t ASC LIMIT $derived_limit
RETURN row.s AS s, row.sl AS sl, row.rel AS rel, row.t AS t, row.tl AS tl, row.prio AS prio, row.lv AS lv, row.sp AS sp, row.tp AS tp
UNION
OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
WITH collect(DISTINCT bf) AS bfs
OPTIONAL MATCH (f0:Fact {id: $id})
WITH bfs, collect(f0) AS f0s
WITH bfs + f0s AS fr
WITH fr, fr AS seen, [y IN fr | {f: y, lv: 1}] AS el
UNWIND CASE WHEN size(fr) = 0 OR $depth < 2 THEN [null] ELSE fr END AS a2
OPTIONAL MATCH (a2)-[:DERIVED_FROM]->(n2:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n2) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 2}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 3 THEN [null] ELSE fr END AS a3
OPTIONAL MATCH (a3)-[:DERIVED_FROM]->(n3:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n3) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 3}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 4 THEN [null] ELSE fr END AS a4
OPTIONAL MATCH (a4)-[:DERIVED_FROM]->(n4:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n4) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 4}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 5 THEN [null] ELSE fr END AS a5
OPTIONAL MATCH (a5)-[:DERIVED_FROM]->(n5:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n5) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 5}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 6 THEN [null] ELSE fr END AS a6
OPTIONAL MATCH (a6)-[:DERIVED_FROM]->(n6:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n6) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 6}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 7 THEN [null] ELSE fr END AS a7
OPTIONAL MATCH (a7)-[:DERIVED_FROM]->(n7:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n7) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 7}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 8 THEN [null] ELSE fr END AS a8
OPTIONAL MATCH (a8)-[:DERIVED_FROM]->(n8:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n8) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 8}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 9 THEN [null] ELSE fr END AS a9
OPTIONAL MATCH (a9)-[:DERIVED_FROM]->(n9:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n9) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 9}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 10 THEN [null] ELSE fr END AS a10
OPTIONAL MATCH (a10)-[:DERIVED_FROM]->(n10:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n10) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 10}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 11 THEN [null] ELSE fr END AS a11
OPTIONAL MATCH (a11)-[:DERIVED_FROM]->(n11:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n11) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 11}] AS el, fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 12 THEN [null] ELSE fr END AS a12
OPTIONAL MATCH (a12)-[:DERIVED_FROM]->(n12:Fact)
WITH head(collect(seen)) AS seen, head(collect(el)) AS el, collect(DISTINCT n12) AS nx
WITH seen, el, [y IN nx WHERE NOT y IN seen] AS fr
WITH seen + fr AS seen, el + [y IN fr | {f: y, lv: 12}] AS el, fr
UNWIND el AS e
WITH e.f AS f, e.lv AS lv
MATCH (f)-[:DERIVED_FROM]->(x:Episode)<-[:HAS_EPISODE]-(se:Session)<-[:HAD]-(ha:Agent)
WITH DISTINCT ha, se, min(lv) AS lv ORDER BY lv ASC, ha.id ASC, se.id ASC LIMIT $derived_limit
RETURN ha.id AS s, 'Agent' AS sl, 'HAD' AS rel, se.id AS t, 'Session' AS tl, 4 AS prio, lv,
       {name: ha.name, role: ha.role, harness: ha.harness} AS sp,
       {agent_id: se.agent_id, started_at: se.started_at} AS tp
