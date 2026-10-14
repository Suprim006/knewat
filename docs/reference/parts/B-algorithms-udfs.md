# B — Graph algorithms, UDFs, FLEX (FalkorDB, for Track 02 "Agent Memory and Coordination")

Source: 62 pages under docs.falkordb.com (`/algorithms/*`, `/udfs/*`). Tags: **[V6.0.2]** = I ran it on local FalkorDB 6.0.2 (graph `zz_B_*`, UDF libs `ZzB*`; all deleted afterwards). **[CONFLICT]** = docs disagree with each other or with 6.0.2. Anything marked "not documented" is absent from these pages.

## 1. Algorithms

All are procedures invoked as `CALL algo.<name>(...) YIELD ...` and run on GraphBLAS sparse matrices ([overview](https://docs.falkordb.com/algorithms/index.md)). Names are case-insensitive [V6.0.2] (`algo.bfs` and `algo.BFS` both work). In 6.0.2 `dbms.procedures()` lists them as READ mode [V6.0.2]. Most take an optional config map with `nodeLabels` / `relationshipTypes` filters ([overview FAQ](https://docs.falkordb.com/algorithms/index.md)).

**Procedures present in 6.0.2 [V6.0.2]:** `algo.BFS, algo.HarmonicCentrality, algo.MSF, algo.SPpaths, algo.SSpaths, algo.WCC, algo.betweenness, algo.labelPropagation, algo.maxFlow, algo.pageRank`. **`algo.AStar` is documented but NOT present** in the 6.0.2 image (`Unknown function 'algo.AStar'`) **[CONFLICT: docs newer than image]**.

### 1.1 Reference table

| Algo | Exact CALL signature | Config keys (default) | YIELD | Complexity / notes |
|---|---|---|---|---|
| [BFS](https://docs.falkordb.com/algorithms/bfs.md) | `CALL algo.bfs(start_node, max_depth, relationship) YIELD nodes, edges` | positional: `start_node` Node (required), `max_depth` Integer (required), `relationship` String\|null (null = all types) | `nodes` List (visited, BFS order), `edges` List (traversed) | No complexity stated; visited set kept in memory, depth blows up exponentially on dense graphs. Doc says null start node raises error; **[V6.0.2] `algo.bfs(null,2,null)` returned empty, no error [CONFLICT]**. **[V6.0.2] `nodes` excludes the start node and is flat (not per-level)**; the doc's `nodes[2]` "depth 2" example is therefore only coincidentally right — compute depth yourself. |
| [SPpaths](https://docs.falkordb.com/algorithms/sppath.md) | `CALL algo.SPpaths({sourceNode:<node>, targetNode:<node>, relTypes:[..], weightProp:<prop>, costProp:<prop>, maxCost:<int>, maxLen:<int>, relDirection:"outgoing", pathCount:<int>}) YIELD path, pathWeight, pathCost` | `relTypes`; `weightProp` = property minimised; `costProp`+`maxCost` = constraint (optional); `maxLen` hops (optional); `relDirection` `outgoing` (default per [FAQ](https://docs.falkordb.com/algorithms/sppath.md)) / `incoming` / `both`; `pathCount` 1 default, 0 = all shortest, n = up to n | `path`, `pathWeight` (Integer), `pathCost` (Integer, if costProp used) | Point-to-point Dijkstra-style; no path ⇒ empty result, no error. [V6.0.2] omitting `weightProp` works (hop count, `pathCost`=0); `costProp:'cost', maxCost:3, pathCount:0` correctly dropped the over-budget path. |
| [SSpaths](https://docs.falkordb.com/algorithms/sspath.md) | `CALL algo.SSpaths({sourceNode:<node>, relTypes:[..], weightProp:<prop>, costProp:<prop>, maxCost:<int>, maxLen:<int>, relDirection:"outgoing", pathCount:<int>}) YIELD path, pathWeight, pathCost` | same as SPpaths minus `targetNode`; `weightProp` optional (omitted ⇒ equal weights ⇒ fewest hops, per [FAQ](https://docs.falkordb.com/algorithms/sspath.md)) | same | One source → all reachable nodes. `pathCount` caps total returned (docs use 1000 / 5 / 10). [V6.0.2] result rows were ordered shortest-first for a weighted run. |
| [AStar](https://docs.falkordb.com/algorithms/astar.md) | `CALL algo.AStar({sourceNode, targetNode, relTypes, weightProp, latitudeProperty, longitudeProperty, heuristicScale, relDirection, pathCount}) YIELD path, pathWeight` | `heuristicScale` 1.0 (must be ≥0; scale = lower bound of weight per metre, else sub-optimal); `relDirection` outgoing; `pathCount` 1 (≥1) | `path`, `pathWeight` (Float) | Needs numeric lat/lon (decimal degrees) on every visited node; haversine heuristic. **Not in 6.0.2.** Useless for non-spatial memory graphs. |
| [PageRank](https://docs.falkordb.com/algorithms/pagerank.md) | `CALL algo.pageRank(label, relationship-type) YIELD node, score` | positional `label` String\|null, `relationship-type` String\|null (null = all) | `node`, `score` Float | Scores sum to 1.0, power-law; directed (incoming links count). No iterations/damping params documented. [V6.0.2] `algo.pageRank(null,null)` works; isolated nodes still get a baseline score. |
| [Betweenness](https://docs.falkordb.com/algorithms/betweenness-centrality.md) | `CALL algo.betweenness({nodeLabels:[..], relationshipTypes:[..], samplingSize:<int>, samplingSeed:<int>}) YIELD node, score` | `nodeLabels` [] (all); `relationshipTypes` [] (all); `samplingSize` 32; `samplingSeed` 0 (= time-based, non-reproducible) | `node`, `score` Float | Sampled approximation from `samplingSize` random source nodes; expensive on big dense graphs. Fix `samplingSeed` for reproducible runs. |
| [Harmonic centrality](https://docs.falkordb.com/algorithms/harmonic-centrality.md) | `CALL algo.HarmonicCentrality([config]) YIELD node, score, reachable` | `nodeLabels` [], `relationshipTypes` [] (both error if the name doesn't exist, per doc) | `node`, `score` Float (Σ 1/d(u,v)), `reachable` Integer (only populated if yielded) | **Approximate** (HyperLogLog + GraphBLAS); directed; unreachable contributes 0 so OK on disconnected graphs. [V6.0.2] unknown `relationshipTypes` errors (`Relationship type 'NOPE' does not exist`) but unknown `nodeLabels` returned 0 rows, no error **[CONFLICT]**; `reachable` includes the node itself; scores slightly off exact (2.5056 vs exact 2.5). |
| [CDLP](https://docs.falkordb.com/algorithms/cdlp.md) | `CALL algo.labelPropagation([config]) YIELD node, communityId` | `nodeLabels` all; `relationshipTypes` all; `maxIterations` 10 | `node`, `communityId` Integer | O(m+n) per iteration; random node order ⇒ **non-deterministic** across runs; no community count needed. |
| [WCC](https://docs.falkordb.com/algorithms/wcc.md) | `CALL algo.WCC([config]) YIELD node, componentId` (docs also call `algo.WCC(null)`) | `nodeLabels` all; `relationshipTypes` all | `node`, `componentId` Integer | O(V+E); ignores edge direction. |
| [MSF](https://docs.falkordb.com/algorithms/msf.md) | `CALL algo.MSF(config) YIELD edges, nodes` | `nodeLabels` all; `relationshipTypes` all; `objective` `'minimize'` (or `'maximize'`); `weightAttribute` (unset = unweighted) | one row per tree: `edges` List, `nodes` List | O(E log V), O(V+E) space; treats edges as undirected; forest has N−C edges; edges missing the weight attr used only if nothing else connects the component. [V6.0.2] isolated node = its own tree with empty `edges`; `objective:'maximize'` works. |
| [MaxFlow](https://docs.falkordb.com/algorithms/maxflow.md) | `CALL algo.maxFlow(config) YIELD nodes, edges, edgeFlows, maxFlow` | **required**: `sourceNodes` [nodes], `targetNodes` [nodes], `relationshipTypes`; `capacityProperty` `'capacity'`; `nodeLabels` all | single row: `nodes`, `edges` (positive-flow only), `edgeFlows` (parallel to `edges`), `maxFlow` Integer | Docs: O(V·E²) ("capacity-scaling", virtual super-source/sink with infinite capacity). [V6.0.2] `edgeFlows` came back as floats (`2.000000`), `maxFlow` as integer. |

Pointers (not procedures): `shortestPath()` / `allShortestPaths()` are Cypher path functions, documented under [`/cypher/functions#path-functions`](https://docs.falkordb.com/algorithms/index.md) (linked from the algorithms overview). [V6.0.2] `length(shortestPath((s)-[:REL*]->(t)))` works; `allShortestPaths` inside `MATCH p=allShortestPaths((s:L{..})-[:R*]->(t:L{..}))` fails with `Source and destination must already be resolved to call allShortestPaths` — bind `s` and `t` in a prior `MATCH` first. Hop-count only; use `algo.SPpaths` for weights.

### 1.2 Examples (from docs)

```cypher
MATCH (alice:Person {name:'Alice'}) CALL algo.bfs(alice, 2, 'FRIEND') YIELD nodes RETURN nodes
CALL algo.pageRank('Paper','CITES') YIELD node, score RETURN node.title, score ORDER BY score DESC
CALL algo.betweenness({nodeLabels:['Person'], relationshipTypes:['FRIEND'], samplingSeed:42}) YIELD node, score
CALL algo.labelPropagation({maxIterations:5}) YIELD node, communityId RETURN communityId, collect(node.name)
CALL algo.WCC(null) YIELD node, componentId RETURN componentId, collect(node.name)
CALL algo.MSF({weightAttribute:'cost'}) YIELD edges, nodes RETURN edges, nodes
MATCH (s:Node{name:'A'}),(t:Node{name:'C'}) CALL algo.maxFlow({sourceNodes:[s],targetNodes:[t],capacityProperty:'cap',relationshipTypes:['PIPE']}) YIELD maxFlow RETURN maxFlow
MATCH (a:City{name:'A'}),(g:City{name:'G'}) CALL algo.SPpaths({sourceNode:a,targetNode:g,relTypes:['Road'],weightProp:'dist',costProp:'time',maxCost:12,pathCount:2}) YIELD path,pathWeight,pathCost RETURN pathWeight,pathCost
```

### 1.3 How an AI agent can use each as a memory tool (my suggestions, not from docs)

| Algo | Agent-tool idea |
|---|---|
| BFS | `expand_context(memory, depth, rel)`: pull the k-hop neighbourhood of a retrieved memory/entity into the prompt; cap `max_depth` ≤2–3 to avoid blow-up. Remember the start node is not in `nodes`. |
| SPpaths | `explain_link(a, b)`: cheapest explanation path between two memories; set `weightProp` = (1 − confidence) or recency-decay cost, `costProp`+`maxCost` = token budget, `pathCount` 3 for alternative justifications. |
| SSpaths | `reachable_within(source, budget)`: all memories reachable under a cost cap, ranked — a graph-aware retrieval pass after vector search. |
| AStar | Skip (needs lat/lon; absent in 6.0.2). Only for geo-tagged memories. |
| PageRank | `core_memories()`: which memories/entities are most referenced → protect from eviction, surface as "key facts", seed summaries. Run on a label (`'Memory'`) + `'REFERS_TO'` type. |
| Betweenness | `bridge_memories()`: memories that connect otherwise separate topics → good anchors for cross-topic reasoning; also risky-to-delete nodes. Use `samplingSeed` for stable output. |
| Harmonic | `central_entities()`: nodes that reach many others fast (good entry points for traversal/routing between agents' sub-graphs); safe on fragmented graphs; directed, so orient edges accordingly. |
| CDLP | `consolidate_topics()`: topic clusters → summarise each cluster into one node during memory consolidation. Non-deterministic: persist `communityId` result rather than recomputing in queries. |
| WCC | `find_islands()`: isolated knowledge islands/orphans (component of size 1–2) → candidates for linking, pruning, or "needs more context"; `count(DISTINCT componentId)` as a graph-health metric. |
| MSF | `skeleton()`: backbone of the memory graph (min-cost tree per component; `maximize` on a similarity/strength weight gives the strongest-link backbone) → compact context tree or pruning of redundant edges. |
| MaxFlow | `capacity_between(agents/queues)`: throughput through a task/agent-handoff network (edge `capacity` = rate limit); also bipartite assignment of tasks to agents. |

## 2. UDFs (User Defined Functions)

Source: [UDF index](https://docs.falkordb.com/udfs/index.md) unless noted.

- **Language:** JavaScript. Library script registers functions via the global `falkor` object; once loaded they are called like built-ins as `LibraryName.FunctionName(args)` (e.g. `StringUtils.UpperCaseOdd('abcdef')`).
- **Read-only:** "UDFs are not allowed to modify the graph in any way" (no update/add/delete). [V6.0.2] assigning `n.name='hacked'` inside a UDF only changed the JS copy; the stored node was unchanged. They can be used in `GRAPH.RO_QUERY` [V6.0.2].
- **Errors:** `throw new Error('x')` → query error `UDF Exception: x` [V6.0.2].
- **Limits:** none listed on the UDF pages. In the [configuration page](https://docs.falkordb.com/getting-started/configuration.md) (outside my page list): `JS_HEAP_SIZE` default 268435456 (256 MB), min 1048576; `JS_STACK_SIZE` default 1048576 (1 MB), min 1048576. Both confirmed via `GRAPH.CONFIG GET *` [V6.0.2]. No documented timeout, sandbox, or network/file API.

### 2.1 Commands

| Command | Notes |
|---|---|
| `GRAPH.UDF LOAD [REPLACE] <Lib> <script>` | Adds a library (many functions per library; un-registered helper functions stay private). Without `REPLACE`, an existing name fails: `Failed to register UDF library 'X': library already registered` [V6.0.2]. |
| `GRAPH.UDF LIST [Lib] [WITHCODE]` | Reply fields: `library_name`, `functions`, `library_code` (with WITHCODE). |
| `GRAPH.UDF DELETE <library>` | Removes one library. |
| `GRAPH.UDF FLUSH` | Removes **all** libraries. |

Python client (FalkorDB-PY, [docs](https://docs.falkordb.com/udfs/index.md)): `db.udf_load(lib, script)`; replace via third arg `db.udf_load(name, content, True)`; `db.udf_list(...)`; `db.udf_delete("Shapes")`; `db.udf_flush()`. Then `db.select_graph("G").query("RETURN StringUtils.UpperCaseOdd('abcdef')")`.
Via redis-cli: `redis-cli -x GRAPH.UDF LOAD MyLib < lib.js` works [V6.0.2].

### 2.2 JS API

- `falkor.register(name, fn)` — expose a function (name, function pointer; both required). `falkor.log(msg)` — log to DB stdout (call returns fine [V6.0.2]).
- **Node:** `.id`, `.labels`, `.attributes`; property access like `n.name` works [V6.0.2]; `n.getNeighbors({direction:'incoming'|'outgoing'|'both', types:[..], labels:[..], returnType:'nodes'|'edges'})` (config optional).
- **Edge:** `.id`, `.type`, `.source`, `.target`, `.attributes`. **Path:** `.nodes`, `.length`, `.relationships`.
- **Global `graph`:** `graph.traverse(sources, config)` (multi-source `getNeighbors`; `targets[i]` = neighbours of source i; faster than many `getNeighbors` calls [V6.0.2 works, returns one array per source]); `graph.getNodeById(id)` (null if absent); `graph.iterateNodes(label)` and `graph.iterateEdges(relType)` (use `for...of`).
- **Breaking change v4.16:** `falkor.traverse()` removed → use `graph.traverse()` (same args).
- UDFs in one library can call each other's helpers; cross-library calls shown in docs by loading `collection` and `similarity` libraries (Jaccard on neighbour IDs; custom DFS `CollectIncreasingAmounts`).

Minimal example (docs):
```javascript
function Area(s){ return (s.a*s.b)/2 }
falkor.register('Area', Area);
```
```cypher
WITH Shapes.RandomShape() AS s WHERE s.a > 1 CREATE (p:Position {area: Shapes.Area(s)}) RETURN s
```

Agent-memory use: scoring UDFs (recency × importance decay, custom ranking in `ORDER BY`), custom traversals that Cypher can't express (e.g. DFS with accumulated constraint), neighbour-set Jaccard between memories. UDFs cannot write — persist results with a normal `SET` in the query.

## 3. FLEX (FalkorDB Library for EXtensions)

[FLEX index](https://docs.falkordb.com/udfs/flex/index.md): open-source UDF package ([github.com/FalkorDB/flex](https://github.com/FalkorDB/flex)); **must be loaded separately** as a UDF library. Docs call it "Library of Extensions" on the UDF page and "Library for Extensions" on the FLEX page (trivial naming inconsistency).

**Load (docs say only "load as a UDF library"; exact commands below are from the repo README, outside the 62 pages):**
```bash
curl -L -o flex.js https://github.com/FalkorDB/flex/releases/latest/download/flex.js
redis-cli GRAPH.UDF LOAD flex "$(cat flex.js)"
```
Library name must be `flex` to get the documented `flex.<category>.<fn>()` calls (calls = `<LibName>.<category>.<fn>`). I loaded it as `ZzBflex` [V6.0.2]: `GRAPH.UDF LIST` showed exactly the 41 functions below, registered as `text.levenshtein`, `sim.jaccard`, etc.

**Cross-cutting [V6.0.2]:**
- Text functions return `null` on null ([text index](https://docs.falkordb.com/udfs/flex/text/index.md)); `levenshtein(null,'abc')`=3 (null ≈ empty string). Collection/map/JSON functions never mutate input ([coll](https://docs.falkordb.com/udfs/flex/collections/index.md), [map](https://docs.falkordb.com/udfs/flex/map/index.md)); JSON parsers return `{}`/`[]` on bad input instead of erroring ([json](https://docs.falkordb.com/udfs/flex/json/index.md)).
- **Date inputs [CONFLICT]:** docs examples use `datetime('2024-03-15T14:30:45Z')`, but `datetime()` is **"Unknown function" on 6.0.2**. Working inputs [V6.0.2]: epoch-millisecond numbers, ISO strings (`'2024-03-15T14:30:45Z'`), `localdatetime(...)`. `date.format` uses tokens `YYYY MM DD HH mm ss SSS [Z]`; the [date index FAQ](https://docs.falkordb.com/udfs/flex/date/index.md) example `'yyyy-MM-dd'` doesn't match the [format page](https://docs.falkordb.com/udfs/flex/date/format.md).
- [truncate FAQ](https://docs.falkordb.com/udfs/flex/date/truncate.md) lists `second` but the units table doesn't; `'second'` worked on 6.0.2 **[CONFLICT, harmless]**. Week = Monday start (2024-03-15 → 2024-03-11 ✓).
- Bitwise ops are 32-bit signed JS ints ([bitwise pages](https://docs.falkordb.com/udfs/flex/bitwise/index.md)).

### 3.1 Every FLEX function (41)

★ = most useful for agent memory.

| Fn | Signature | Purpose |
|---|---|---|
| ★[sim.jaccard](https://docs.falkordb.com/udfs/flex/similarity/jaccard.md) | `flex.sim.jaccard(list1, list2)` | Jaccard of two lists as sets, 0–1 (`null` if not arrays). Tag/entity overlap between memories. [V6.0.2] 0.5 for `['a','b','c']` vs `['b','c','d']`. |
| ★[text.levenshtein](https://docs.falkordb.com/udfs/flex/text/levenshtein.md) | `flex.text.levenshtein(string1, string2)` | Edit distance (int), case-sensitive (wrap with `toLower()`). Entity dedup, `<= 2` threshold. [V6.0.2] kitten/sitting=3. |
| ★[text.jaroWinkler](https://docs.falkordb.com/udfs/flex/text/jaroWinkler.md) | `flex.text.jaroWinkler(string1, string2)` | Similarity 0–1, prefix-weighted, good for names; case-sensitive. Dedup with `> 0.85`. [V6.0.2] Martha/Marhta=0.961. |
| [text.capitalize](https://docs.falkordb.com/udfs/flex/text/capitalize.md) | `flex.text.capitalize(string)` | Uppercase first char only. |
| [text.decapitalize](https://docs.falkordb.com/udfs/flex/text/decapitalize.md) | `flex.text.decapitalize(string)` | Lowercase first char only. |
| [text.swapCase](https://docs.falkordb.com/udfs/flex/text/swapCase.md) | `flex.text.swapCase(string)` | Invert case of every letter. |
| ★[text.camelCase](https://docs.falkordb.com/udfs/flex/text/camelCase.md) | `flex.text.camelCase(string)` | → `helloWorld`; strips non-alphanumerics. |
| [text.upperCamelCase](https://docs.falkordb.com/udfs/flex/text/upperCamelCase.md) | `flex.text.upperCamelCase(string)` | → `HelloWorld` (PascalCase). |
| ★[text.snakeCase](https://docs.falkordb.com/udfs/flex/text/snakeCase.md) | `flex.text.snakeCase(string)` | → `hello_world`; normalise relation/property names. |
| [text.format](https://docs.falkordb.com/udfs/flex/text/format.md) | `flex.text.format(template, parameters)` | `{0}`,`{1}` placeholders from a list; null template → null. |
| [text.indexOf](https://docs.falkordb.com/udfs/flex/text/indexOf.md) | `flex.text.indexOf(string, substring, offset, to)` | First index (0-based) or −1; `offset` default 0, `to` default −1. |
| [text.indexesOf](https://docs.falkordb.com/udfs/flex/text/indexesOf.md) | `flex.text.indexesOf(string, substring, from, to)` | List of all indices; `[]` if none. |
| [text.join](https://docs.falkordb.com/udfs/flex/text/join.md) | `flex.text.join(array, delimiter)` | Join list with delimiter. |
| [text.lpad](https://docs.falkordb.com/udfs/flex/text/lpad.md) | `flex.text.lpad(string, length, padChar)` | Left-pad (padChar default space; numbers auto-stringified). |
| [text.rpad](https://docs.falkordb.com/udfs/flex/text/rpad.md) | `flex.text.rpad(string, length, padChar)` | Right-pad. |
| ★[text.regexGroups](https://docs.falkordb.com/udfs/flex/text/regexGroups.md) | `flex.text.regexGroups(string, regex)` | All global matches as `[full, group1, ...]` lists. Pull entities/dates out of free text. [V6.0.2] `'a1b22'` with `([a-z])(\\d+)` → `[[a1,a,1],[b22,b,22]]` (double the backslash in the query string). |
| [text.repeat](https://docs.falkordb.com/udfs/flex/text/repeat.md) | `flex.text.repeat(string, count)` | Repeat string (count ≥ 0). |
| ★[text.replace](https://docs.falkordb.com/udfs/flex/text/replace.md) | `flex.text.replace(string, regex, replacement)` | **Regex** global replace (not literal). Sanitise memory text. |
| ★[coll.frequencies](https://docs.falkordb.com/udfs/flex/collections/frequencies.md) | `flex.coll.frequencies(list)` | Map element→count (keys stringified; null → key `"null"`; non-array → `{}`). Tag/entity counts. |
| ★[coll.intersection](https://docs.falkordb.com/udfs/flex/collections/intersection.md) | `flex.coll.intersection(list1, list2)` | Common elements, order of list1. |
| [coll.shuffle](https://docs.falkordb.com/udfs/flex/collections/shuffle.md) | `flex.coll.shuffle(list)` | Fisher-Yates shuffle (new list); random sampling/negative examples. |
| ★[coll.union](https://docs.falkordb.com/udfs/flex/collections/union.md) | `flex.coll.union(list1, list2)` | Unique elements of both; order not guaranteed. Merge/dedup lists when merging duplicate entities. |
| [coll.zip](https://docs.falkordb.com/udfs/flex/collections/zip.md) | `flex.coll.zip(list1, list2)` | Pairs `[a,b]`, length of the shorter list. |
| ★[date.format](https://docs.falkordb.com/udfs/flex/date/format.md) | `flex.date.format(datetime, pattern, timezone)` | Token pattern (default `'YYYY-MM-DDTHH:mm:ss[Z]'`), optional offset like `"+02:00"`. UTC internally. |
| ★[date.parse](https://docs.falkordb.com/udfs/flex/date/parse.md) | `flex.date.parse(dateString, pattern, timezone)` | Patterns `'YYYY-MM-DD'`, `'YYYY-MM-DDTHH:mm:ss'`, `'YYYY-MM-DD HH:mm:ss'` or auto (JS Date fallback); null on failure. |
| [date.toTimeZone](https://docs.falkordb.com/udfs/flex/date/toTimeZone.md) | `flex.date.toTimeZone(datetime, timezone)` | Shifts UTC fields to local wall-clock for offsets `+HH:MM`/`+HHMM`; no DST. [V6.0.2] `+05:45` shifted 14:00Z → 19:45. |
| ★[date.truncate](https://docs.falkordb.com/udfs/flex/date/truncate.md) | `flex.date.truncate(datetime, unit)` | Units `minute, hour, day, week(Mon), month, quarter, year` (UTC). Bucket memories by day/week for time-windowed recall and consolidation. Unknown unit → input returned. |
| [json.toJson](https://docs.falkordb.com/udfs/flex/json/toJson.md) | `flex.json.toJson(value)` | Serialise value to JSON string (null on failure). Store structured payloads in one property. |
| [json.fromJsonMap](https://docs.falkordb.com/udfs/flex/json/fromJsonMap.md) | `flex.json.fromJsonMap(jsonString)` | Parse object → map; `{}` on error. |
| [json.fromJsonList](https://docs.falkordb.com/udfs/flex/json/fromJsonList.md) | `flex.json.fromJsonList(jsonString)` | Parse array → list; `[]` on error. |
| [map.fromPairs](https://docs.falkordb.com/udfs/flex/map/fromPairs.md) | `flex.map.fromPairs(pairs)` | `[[k,v],...]` → map (last dup wins). |
| ★[map.merge](https://docs.falkordb.com/udfs/flex/map/merge.md) | `flex.map.merge(map1, map2, ...)` | Shallow merge, later wins; e.g. defaults + `properties(n)`. |
| ★[map.submap](https://docs.falkordb.com/udfs/flex/map/submap.md) | `flex.map.submap(map, keys)` | Keep only listed keys. Trim memory payload for prompts. |
| [map.removeKey](https://docs.falkordb.com/udfs/flex/map/removeKey.md) | `flex.map.removeKey(map, key)` | Drop one key. |
| ★[map.removeKeys](https://docs.falkordb.com/udfs/flex/map/removeKeys.md) | `flex.map.removeKeys(map, keys)` | Drop many keys (e.g. embeddings, secrets) before returning to an LLM. |
| [bitwise.and](https://docs.falkordb.com/udfs/flex/bitwise/and.md) | `flex.bitwise.and(a, b)` | AND (flag test). |
| [bitwise.or](https://docs.falkordb.com/udfs/flex/bitwise/or.md) | `flex.bitwise.or(a, b)` | OR (set flags). |
| [bitwise.xor](https://docs.falkordb.com/udfs/flex/bitwise/xor.md) | `flex.bitwise.xor(a, b)` | XOR (toggle). |
| [bitwise.not](https://docs.falkordb.com/udfs/flex/bitwise/not.md) | `flex.bitwise.not(a)` | One's complement (`~n = -(n+1)`). |
| [bitwise.shiftLeft](https://docs.falkordb.com/udfs/flex/bitwise/shiftLeft.md) | `flex.bitwise.shiftLeft(a, positions)` | `<<`. |
| [bitwise.shiftRight](https://docs.falkordb.com/udfs/flex/bitwise/shiftRight.md) | `flex.bitwise.shiftRight(a, positions)` | Sign-propagating `>>`. |

Count check: sim 1 + text 17 + coll 5 + date 4 + json 3 + map 5 + bitwise 6 = 41 (matches the 41 functions registered by the released `flex.js` [V6.0.2]).

## 4. Pages read (62)
Algorithms (12): index, bfs, betweenness-centrality, cdlp, pagerank, sppath, astar, sspath, wcc, harmonic-centrality, maxflow, msf. UDFs (1): udfs/index. FLEX (49): flex/index + 7 category indexes (bitwise, collections, date, json, map, similarity, text) + 41 function pages. Extra (not in list): [configuration](https://docs.falkordb.com/getting-started/configuration.md) for JS_HEAP_SIZE/JS_STACK_SIZE; FLEX GitHub README for load commands.
