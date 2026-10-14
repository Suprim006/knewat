# FalkorDB Cypher Reference + Cookbook (Part A)

Source: all 30 pages of the Cypher area of https://docs.falkordb.com (read in full). Base for links: `https://docs.falkordb.com`. Items tagged **verified on 6.0.2** were run on the local `falkordb-dev` container (graph `zz_A_*`, since deleted). `[CONFLICT]` = docs disagree with each other or with observed 6.0.2 behaviour. FalkorDB implements a *subset* of OpenCypher v9 plus extensions ([index](https://docs.falkordb.com/cypher/index.md), [support](https://docs.falkordb.com/cypher/cypher-support.md)).

Doc links in this file: [index](https://docs.falkordb.com/cypher/index.md) · [cheat-sheet](https://docs.falkordb.com/cypher/cheat-sheet.md) · [datatypes](https://docs.falkordb.com/datatypes.md) · [functions](https://docs.falkordb.com/cypher/functions.md) · [procedures](https://docs.falkordb.com/cypher/procedures.md) · [limitations](https://docs.falkordb.com/cypher/known-limitations.md) · [indexing](https://docs.falkordb.com/cypher/indexing/index.md)

---
## 1. Clauses (syntax + FalkorDB behaviour)

Comments: `// line` and `/* block */` anywhere whitespace is allowed ([index](https://docs.falkordb.com/cypher/index.md)). Queries run via `GRAPH.QUERY` (r/w) or `GRAPH.RO_QUERY` (errors on writes; verified: `graph.RO_QUERY is to be executed only on read-only queries`).

### MATCH ([match](https://docs.falkordb.com/cypher/match.md))
- Entity form `alias:label {filters}` – all parts optional. Nodes `()`, relationships `[]`. Multiple labels `(n:A:B)` = node has all of them ([datatypes](https://docs.falkordb.com/datatypes.md)). Multiple rel types `[r:A|B]` = any of them.
- Direction: `-[:T]->`, `<-[:T]-`, `-[:T]-` (any; each pair returned twice), `<-[:T]->` same as undirected, `--` any rel.
- Variable length: `-[:TYPE*minHops..maxHops]->`; defaults: any type, min 1, max ∞. `*` = 1..∞, `*2` = exactly 2, `*..3` = up to 3, `*1..3`. Hop bounds on `shortestPath`: min may only be 0 or 1 ([functions](https://docs.falkordb.com/cypher/functions.md)).
- Named paths: `MATCH p = (a)-[:T*1..3]->(b)`; includes unaliased intermediates; use `nodes(p)`, `relationships(p)`, `length(p)`; clients can return the path directly.
- Comma-separated patterns allowed: `MATCH (a:X), (b:Y)`.
- Label expressions `(n:A|B)` are **unsupported** ([support](https://docs.falkordb.com/cypher/cypher-support.md); verified parse error). Use `WHERE n:A OR n:B`.

### OPTIONAL MATCH ([optional-match](https://docs.falkordb.com/cypher/optional-match.md))
- LEFT-JOIN semantics; unmatched elements → `null`; accepts the same patterns/`WHERE` (the `WHERE` belongs to the optional pattern).
- Null-lenient: property access / functions on null return null. `SET`, `MERGE`, `DELETE` ignore null inputs. **`CREATE` of a relationship with a null endpoint errors and rolls back everything** (verified: `Invalid node id`).
- Docs say a mandatory `MATCH` cannot follow an `OPTIONAL MATCH`. **[CONFLICT]** verified 6.0.2: `MATCH (a) OPTIONAL MATCH (a)-[:R]->(b) MATCH (c) RETURN count(*)` ran without error. Don't rely on either.

### WHERE ([where](https://docs.falkordb.com/cypher/where.md))
Operators: `= <> < <= > >=`, `CONTAINS`, `STARTS WITH`, `ENDS WITH`, `IN`, `IS [NOT] NULL`, `AND OR NOT XOR`. Inline `{prop: val}` ≡ equality in `WHERE`.
- Pattern predicates: `WHERE (p)-[:WON]->(s)`, `WHERE NOT (p)-[:WON]->(s) AND (p)-[:GOVERNOR]->(s)` (verified).
- Label predicate: `WHERE n:L1 OR n:L2` (put labels in the MATCH pattern when possible – faster).
- `exists(n.prop)` works (verified); `exists((n)-[]->())` is **not supported** (verified: `traversal patterns are not allowed as arguments to exists()`) – use a pattern predicate.
- Regex: docs say `=~` unsupported ([support](https://docs.falkordb.com/cypher/cypher-support.md)). **[CONFLICT]** verified 6.0.2: `WHERE a.n =~ 'A.*'` works. Documented alternative: `string.matchRegEx()`.
- `WHERE` after `WITH` is evaluated *after* writes that preceded that `WITH` (sees post-write state) ([with](https://docs.falkordb.com/cypher/with.md)).

### RETURN / ORDER BY / SKIP / LIMIT ([return](https://docs.falkordb.com/cypher/return.md), [order-by](https://docs.falkordb.com/cypher/order-by.md), [skip](https://docs.falkordb.com/cypher/skip.md), [limit](https://docs.falkordb.com/cypher/limit.md))
- `RETURN [DISTINCT] expr [AS alias], …`; returning a bare alias returns the full entity. No `GROUP BY`: non-aggregated items become implicit grouping keys.
- `ORDER BY expr [ASC|ASCENDING|DESC|DESCENDING], …` (default ASC); may use aliases/aggregations from RETURN/WITH.
- `SKIP n` / `LIMIT n`; no default limit. Always pair with `ORDER BY` for deterministic paging (`ORDER BY p.name SKIP 100 LIMIT 100`).
- **LIMIT does not stop eager ops**: `UNWIND [1,2,3] AS v CREATE (a {property: v}) RETURN a LIMIT 1` creates 3 nodes, returns 1. Affects CREATE, SET, DELETE, MERGE and aggregating projections ([limitations](https://docs.falkordb.com/cypher/known-limitations.md)).

### WITH ([with](https://docs.falkordb.com/cypher/with.md))
Pipeline between query parts; only listed variables survive; supports `AS`, `DISTINCT`, `ORDER BY`, `SKIP`, `LIMIT`, aggregation (implicit grouping), and a following `WHERE`. It can feed writes: `MATCH (u:User) WITH u AS nonrecent ORDER BY u.lastVisit LIMIT 3 SET nonrecent.should_contact = true`.

### UNWIND ([unwind](https://docs.falkordb.com/cypher/unwind.md))
`UNWIND <list> AS x` → one row per element, order kept; inverse of `collect()`. Empty list → zero rows (downstream clauses don't run; verified `UNWIND [] AS x CREATE (:Zed)` is a no-op). Works on list-of-maps (`UNWIND $rows AS r … r.field`).

### UNION ([union](https://docs.falkordb.com/cypher/union.md))
`q1 UNION [ALL] q2` – column count and **names** must be identical (use `AS`). `UNION` dedups, `UNION ALL` keeps duplicates. `ORDER BY` applies to the combined result; per-branch ORDER BY only inside `CALL {}`.

### CREATE ([create](https://docs.falkordb.com/cypher/create.md))
`CREATE (n)`, `CREATE (n),(m)`, `CREATE (:Person {name:'Kurt', age:27})`, `MATCH (a:Person) WHERE a.name='Kurt' CREATE (a)-[:MEMBER]->(:Band {name:'Nirvana'})`, whole patterns `CREATE (jim:Person{…})-[:FRIENDS]->(pam:Person{…})-[:WORKS]->(:Employer{…})`. Bound (matched) aliases are reused; unbound ones are created. Label-less nodes are allowed. Property values must be storable (see §5).

### MERGE ([merge](https://docs.falkordb.com/cypher/merge.md))
- `MERGE <pattern> [ON CREATE SET …] [ON MATCH SET …]`.
- Whole path is matched *or* created: if any part is missing, **all** MERGE-introduced elements are created (duplicates!). Merge each node in its own clause, then merge the relationship: `MERGE (a {name:'X'}) MERGE (b:Movie {name:'Y'}) MERGE (a)-[r:ACTED_IN]->(b)`.
- Aliases bound by earlier clauses are only matched, never created → `MATCH (a) MATCH (b) MERGE (a)-[:R]->(b)` creates the edge only if both ends exist.
- Verified 6.0.2: second identical `MERGE … ON CREATE SET … ON MATCH SET …` took the ON MATCH branch; `SET p += r` after `MERGE (p {id:r.id})` inside `UNWIND` works.
- Races: MERGE is not a uniqueness guarantee on its own; combine with a UNIQUE constraint (§4).

### SET ([set](https://docs.falkordb.com/cypher/set.md))
`SET n.p = v, n.q = w` · `SET n = {map}` (**replaces all** props) · `SET n += {map}` (merge, keep others) · `SET a = b` (copy all props from entity b) · `SET n.p = NULL` (removes prop). `SET n += {x:1, y:null}` sets x and drops/ignores y (verified). `SET a = row` with a LOAD CSV row works. `SET n:Label` adds a label – **not on the SET doc page, verified on 6.0.2** (`SET m:Hot` → `labels(m)=[Mem, Hot]`).

### REMOVE ([remove](https://docs.falkordb.com/cypher/remove.md))
`REMOVE n.prop` · `REMOVE n:Label` · `REMOVE n:A:B`. Equivalent to `SET n.prop = NULL` for properties. Removing all labels leaves `labels(n)=[]` (verified).

### DELETE ([delete](https://docs.falkordb.com/cypher/delete.md))
`MATCH (p {name:'Jim'}) DELETE p` removes node **and all its relationships** (FalkorDB always behaves as DETACH DELETE; `DETACH DELETE` is accepted and identical; verified: "Relationships deleted: 2"). `MATCH ()-[r:FRIENDS]->() DELETE r` deletes only edges. Wipe: `MATCH (n) DETACH DELETE n` (or `GRAPH.DELETE`).

### FOREACH ([foreach](https://docs.falkordb.com/cypher/foreach.md))
`FOREACH (x IN list | <updating clauses: CREATE MERGE SET REMOVE DELETE FOREACH>)`. Rows pass through unchanged; inner variables are local; no MATCH/RETURN inside. Conditional write: `FOREACH(_ IN CASE WHEN cond THEN [1] ELSE [] END | …)` (verified).

### CALL {} subqueries ([call](https://docs.falkordb.com/cypher/call.md))
Runs once per input row. Returning subquery may change row count; non-returning (no RETURN) keeps rows (side effects). **Import outer variables only via an opening `WITH`** (`WITH n, m` simple projections, or `WITH *`). Returned names must not shadow outer variables. Supports `UNION` inside (post-union processing: aggregate/SET on the union result). Verified: per-row `CALL { WITH a MATCH (a)-[r:KNOWS]->() RETURN count(r) AS c }` and UNION inside CALL.

### CALL procedure ([procedures](https://docs.falkordb.com/cypher/procedures.md))
`CALL db.labels()`; `CALL proc(args) YIELD col [AS alias] [WHERE …] RETURN …`. `YIELD` optional (omitted → all columns). Can be interleaved with other clauses, e.g. `CALL db.idx.fulltext.queryNodes('Movie','Book') YIELD node AS m WHERE m.genre='Adventure' RETURN m ORDER BY m.rating` ([fulltext](https://docs.falkordb.com/cypher/indexing/fulltext-index.md)).

### LOAD CSV ([load-csv](https://docs.falkordb.com/cypher/load-csv.md))
`LOAD CSV [WITH HEADERS] FROM '<file://name.csv | https://…>' AS row [FIELDTERMINATOR ';']`. Every value is a **string** → cast with `toInteger/toFloat/toBoolean`. Without headers `row` is a list (`row[0]`); with headers it's a map (`row['name']`). `file://` URIs resolve under the configured `IMPORT_FOLDER`; remote must be HTTPS. Many/missing columns: `CREATE (a:Actor) SET a = row` (missing entries simply absent). **[CONFLICT/typo]** doc example `row[name]` should be `row['name']`.

### Other (not documented as clauses)
`CASE` (simple + generic), `reduce`, list/pattern comprehensions – see §2. Schema-retrieval queries are not supported; use `labels()`/`type()` and `db.*` procedures ([support](https://docs.falkordb.com/cypher/cypher-support.md)). `count{}` subquery expressions: not documented; verified parse error on 6.0.2.

---
## 2. Functions ([functions](https://docs.falkordb.com/cypher/functions.md))  (* = FalkorDB extension)

| Group | Functions |
|---|---|
| Predicate | `all/any/none/single(x IN list WHERE pred)`, `exists(n.prop)`, `isEmpty(list\|map\|string)` |
| Scalar | `coalesce(e,…)`, `startNode(r)`, `endNode(r)`, `id()` (internal, **not immutable**), `labels(n)`, `type(r)`, `properties(x)`, `hasLabels(n, [labels])`*, `typeOf(x)`* (→ Map/String/Integer/Boolean/Float/Node/Edge/List/Path/Point/Null; also `Date` etc. verified), `timestamp()` (ms epoch), `randomUUID()`, `prev(expr)`* (previous value, null on first call – var-length edge filtering) |
| Aggregate | `count(x\|*)` (`count(*)` counts nulls), `sum` (0 if empty), `avg`, `min`, `max`, `collect` (skips nulls), `percentileCont/Disc(x,p)`, `stDev`, `stDevP`. `DISTINCT` allowed (verified `count(DISTINCT t)`) |
| List | `head`, `tail`, `last`, `size`, `keys`, `range(first,last[,step])`, `reduce(acc=init, x IN list \| expr)`, `list.dedup`*, `list.sort(list[,asc])`*, `list.insert(list,idx,val[,dups])`*, `list.insertListElements(list,list2,idx[,dups])`*, `list.remove(list,idx[,count])`*; slicing `list[0..2]` (verified) |
| Math ops | `+ - * / ^ %` (verified `7/2=3` integer division, `7.0/2=3.5`, `2^3` → float 8) |
| Math funcs | `abs ceil e exp floor log log10 pow* rand round sign sqrt`; `ceil/floor/round` of an integer stay integer; `round` ties **half away from zero** (verified 2.5→3, -2.5→-3) |
| Trig | `acos asin atan atan2 cos cot degrees haversin pi radians sin tan` |
| String | `left lTrim replace reverse right rTrim split substring(str,start[,len]) toLower toUpper trim size`, `string.join(list[,delim])`*, `string.matchRegEx(s,re)`*, `string.replaceRegEx(s,re,repl)`*, `toJSON(x)`*, `intern(str)`* (dedup memory for repeated strings) |
| Type conv | `toBoolean toFloat toInteger* toString` + `…OrNull` + `…List` variants. `toInteger` of a float floors (verified `-1.5 → -2`) |
| Node | `indegree(node[, reltype…])`*, `outdegree(…)`* |
| Path | `nodes(p)`, `relationships(p)`, `length(p)`, `shortestPath(pattern)`*, `allShortestPaths(pattern)`* |
| Point | `point({latitude:, longitude:})` (case-sensitive keys), `distance(p1,p2)` meters (verified ≈11132 m per 0.1° lat) |
| Vector | `vecf32(list)`, `vec.euclideanDistance(v1,v2)`, `vec.cosineDistance(v1,v2)` |
| Temporal | `date()`, `localtime()`, `localdatetime()`, `duration()` (see §5). Temporal *arithmetic functions* unsupported but `+`/`-` operators work. UDFs via Flex UDF library ([udfs](https://docs.falkordb.com/udfs)) – docs also say "user-defined functions unsupported" in [support](https://docs.falkordb.com/cypher/cypher-support.md) **[CONFLICT]** (support matrix vs FAQ). |

Path-function rules ([functions](https://docs.falkordb.com/cypher/functions.md)): `shortestPath` returns *one* path (NULL if none); arg is a single traversal pattern with **endpoints already resolved** and **no property filters in the pattern**; rel types allowed; `WITH shortestPath((a)-[*]->(g)) AS p`. `allShortestPaths` returns every minimal path; verified it errors unless endpoints are bound in a prior clause (`Source and destination must already be resolved…`) → write `MATCH (a),(d) WITH a,d MATCH p=allShortestPaths((a)-[:R*]->(d))`.

Comprehensions: list `[x IN list WHERE cond | out]` (WHERE and `| out` optional); pattern `[(n)-[e:FRIEND_OF]->(f:Person) WHERE e.since < 2010 | f.age]`; existential `any(e IN relationships(p) WHERE e.weight < 3)`. **Aggregates inside pattern comprehensions error** (`Invalid use of aggregating function 'count'`, verified); aggregate in a preceding `WITH` or use `size()` ([limitations](https://docs.falkordb.com/cypher/known-limitations.md)). Aggregations inside map projections/maps must be computed in a prior `WITH` ([datatypes](https://docs.falkordb.com/datatypes.md)).

Known function discrepancies on **6.0.2**: `datetime()`, `time()`, `vecf64()` → `Unknown function` (verified). The functions FAQ claims `vecf64()` exists **[CONFLICT]**; its own table lists only `vecf32`. `dbms.functions` exists in 6.0.2 `dbms.procedures()` listing – use it to list all functions.

---
## 3. Procedures ([procedures](https://docs.falkordb.com/cypher/procedures.md))

| Procedure | Args | Yields |
|---|---|---|
| `db.labels` / `db.relationshipTypes` / `db.propertyKeys` | – | `label` / `relationshipType` / `propertyKey` |
| `db.meta.stats` | – | `labels, relTypes, relCount, nodeCount, labelCount, relTypeCount, propertyKeyCount` |
| `db.indexes` | – | `label, properties, types, options, language, stopwords, entitytype, status, info` (types RANGE/FULLTEXT/VECTOR[/CCH]) |
| `db.constraints` | – | `type, label, properties, entitytype, status` |
| `db.idx.fulltext.createNodeIndex` | `label, prop…` (or config map as label) | – (WRITE) |
| `db.idx.fulltext.drop` | `label` (drops all FT props of the label) | – (WRITE) |
| `db.idx.fulltext.queryNodes` / `queryRelationships` | `label\|relType, query` | `node\|relationship, score` |
| `db.idx.vector.queryNodes` / `queryRelationships` | `label\|relType, attribute, k, queryVec` | `node\|relationship, score` |
| `algo.pageRank` | `label, relType` | `node, score` |
| `algo.BFS` | `sourceNode, maxLevel (0=unbounded), relType` | `nodes, edges` |
| `algo.WCC` / `algo.MSF` / `algo.betweenness` / `algo.labelPropagation` | `config` map | `node,componentId` / `edges,nodes` / `node,score` / `node,communityId` |
| `algo.SPpaths` / `algo.SSpaths` | `config` map (`sourceNode, targetNode, relTypes, weightProp, pathCount`) | `path, pathWeight, pathCost` |
| `dbms.procedures` | – | `name, mode` (READ/WRITE) |

Algorithm details live in the Algorithms docs (`/algorithms/bfs|wcc|msf|cdlp|betweenness-centrality|sppath|sspath|harmonic-centrality|maxflow`) – out of this part's scope. Verified `dbms.procedures()` on 6.0.2 additionally lists `algo.HarmonicCentrality`, `algo.maxFlow`, `dbms.functions`; it did **not** list `db.idx.cch.query` (see §4). Verified `algo.SPpaths({sourceNode:a,targetNode:d,relTypes:['R'],weightProp:'w',pathCount:1})` → `pathWeight=2, length(path)=2`.

---
## 4. Indexing + constraints

### Range index ([range-index](https://docs.falkordb.com/cypher/indexing/range-index.md))
```
CREATE INDEX FOR (p:Person) ON (p.age)                    // node
CREATE INDEX FOR ()-[f:FOLLOW]-() ON (f.created_at)       // relationship
CREATE INDEX ON :Person(age)                              // old syntax, still accepted
DROP INDEX ON :Person(age)   |   DROP INDEX ON :FOLLOW(created_at)
```
- Types: string, numeric, geospatial point, arrays of scalars (`WHERE 90 IN p.samples` uses it). Not nested arrays/maps/vectors.
- Auto-used for equality, `< <= > >=`, string prefix; **not** `<>` ([limitations](https://docs.falkordb.com/cypher/known-limitations.md)). Geospatial index works only with `<`/`<=` on `distance(e.location, pt) < r`.
- Plan operators: `Node By Index Scan | (p:Person)`, `Edge By Index Scan | [f:FOLLOW]`; without index the doc says `Label Scan`/cheat-sheet says `Node By Label Scan` (**[CONFLICT]** naming; verified 6.0.2 indexed plan prints `Node By Index Scan`).
- Single-property per index in docs. Verified 6.0.2: `CREATE INDEX FOR (p:P2) ON (p.first, p.last)` returned `Indices created: 2` (one per attribute), and re-indexing an indexed attribute errors `Attribute 'n' is already indexed`.
- Costs: write overhead, memory; skip low-cardinality/high-churn props.

### Full-text index ([fulltext-index](https://docs.falkordb.com/cypher/indexing/fulltext-index.md))
```
CREATE FULLTEXT INDEX FOR (n:Movie) ON (n.title) [OPTIONS { language: 'German', stopwords: ['a','ab'] }]
CREATE FULLTEXT INDEX FOR ()-[m:Manager]-() ON (m.name)
DROP FULLTEXT INDEX FOR (n:Movie) ON (n.title)            // drops that property only
CALL db.idx.fulltext.createNodeIndex('Movie','title')     // procedure form; extra props = more args
CALL db.idx.fulltext.createNodeIndex({label:'Movie', language:'German', stopwords:['a','ab']}, 'title')
CALL db.idx.fulltext.createNodeIndex('Movie', {field:'title', phonetic:'dm:en'})   // also weight, nostem
CALL db.idx.fulltext.drop('Movie')                        // drops ALL FT props of label
CALL db.idx.fulltext.queryNodes('Movie','Book') YIELD node, score
CALL db.idx.fulltext.queryRelationships('Manager','Charlie Munger') YIELD relationship, score
```
- RediSearch query syntax: tokenised words; `term*` prefix (end of word only); `a b` = AND; `a|b` = OR; `-term` NOT. Score = TF-IDF. Default stemming/stopwords per language.
- Fuzzy: docs say `%term%distance` (distance 1–3, default 1), e.g. `%Jangle%1`. **[CONFLICT]** verified 6.0.2: `'%dari%'` matched "dark" but `'%dari%1'` and `'%darl%1'` returned **no rows**; `'%%dari%%'` (distance 2) works. Use native RediSearch `%term%` / `%%term%%` / `%%%term%%%`.
- Verified: `dar*`, `dark -chocolate`, `chocolate|hackathon` behave as above; all text-matches return `score` (1 for single-term hits). Plan shows `ProcedureCall | db.idx.fulltext.queryNodes`.
- A DDL-created FT index coexists with range/vector indexes on the same label; `db.indexes()` shows `{emb: [VECTOR], agent: [RANGE], text: [FULLTEXT]}` (verified).

### Vector index ([vector-index](https://docs.falkordb.com/cypher/indexing/vector-index.md))
```
CREATE VECTOR INDEX FOR (p:Product) ON (p.description) OPTIONS {dimension:128, similarityFunction:'euclidean'}
CREATE VECTOR INDEX FOR ()-[e:Call]->() ON (e.summary) OPTIONS {dimension:128, similarityFunction:'euclidean'}
DROP VECTOR INDEX FOR (p:Product) ON (p.description)
CREATE (p:Product {description: vecf32([2.1, 0.82, 1.3])})
CALL db.idx.vector.queryNodes('Product','description', 10, vecf32([...])) YIELD node, score
CALL db.idx.vector.queryRelationships('Call','summary', 10, vecf32([...])) YIELD relationship, score
```
| Option | Req | Default | Notes |
|---|---|---|---|
| `dimension` | yes | – | 1–4096 (HNSW) |
| `similarityFunction` | yes | – | `cosine` \| `euclidean` |
| `M` | no | 16 | recommended 12–48 |
| `efConstruction` | no | 200 | 100–400 |
| `efRuntime` | no | 10 | raise for recall |

- Memory ≈ `vectors × dims × 4 B + ~20%`. Approximate (ANN) results. **No property filtering inside the index query** ([vector-index](https://docs.falkordb.com/cypher/indexing/vector-index.md)); verified: you *can* post-filter with `YIELD node, score WHERE node.agent='a1'` but k is applied first (a k=3 query returned only the 2 `a1` hits).
- **[CONFLICT – important] score direction.** Cheat-sheet says cosine "higher is more similar, sort DESC", and the vector page example sorts `ORDER BY score DESC`. **Verified on 6.0.2:** with `cosine`, `score` is a *distance*: identical vector → `7.7e-08`, vector at cosine distance 0.78 → `0.78`; `vec.cosineDistance(orthogonal)=1`. So **lower score = nearer; sort ASC** for both metrics. Always confirm with a known pair before ranking.
- Verified: inserting a `vecf32` of the wrong dimension (2 vs index 3) was **accepted without error** (node simply not meaningfully indexed) – validate dimensions client-side. Plan shows `Node By Vector Index Scan`. FAQ says "any dimension" vs 1–4096 elsewhere **[CONFLICT]**.
- `vec.cosineDistance`/`euclideanDistance` work without an index.

### CCH index ([cch-index](https://docs.falkordb.com/cypher/indexing/cch-index.md))
`CREATE CCH INDEX FOR ()-[e:ROAD|FERRY]->() ON (e.w)`; `DROP CCH INDEX FOR … ON (e.w)`; query `MATCH (a),(b) CALL db.idx.cch.query({sourceNode:a,targetNode:b,relTypes:['ROAD'],weightProp:'w'}) YIELD pathWeight, path` (read-only; works with `GRAPH.RO_QUERY`). Relationship-only, one weight property, multi-type allowed (only index type that is), missing weight = 1, parallel edges → cheapest, direction respected, unreachable → zero rows, same node → weight 0. Auto-maintained; weight changes cheap, topology changes rebuild. **Verified NOT available on 6.0.2:** `CREATE CCH INDEX …` → parse error; `db.idx.cch.query` → `Unknown function`. Treat as newer than the pinned image; use `algo.SPpaths` instead.

### Constraints (not Cypher DDL; Redis commands – [cheat-sheet](https://docs.falkordb.com/cypher/cheat-sheet.md))
```
GRAPH.QUERY g "CREATE INDEX FOR (p:Person) ON (p.first_name, p.last_name)"   # prerequisite for UNIQUE
GRAPH.CONSTRAINT CREATE g UNIQUE    NODE Person PROPERTIES 2 first_name last_name
GRAPH.CONSTRAINT CREATE g MANDATORY NODE Person PROPERTIES 1 id
GRAPH.CONSTRAINT DROP   g MANDATORY NODE Person PROPERTIES 1 id
CALL db.constraints()    // type,label,properties,entitytype,status
```
Async build: reply `PENDING`; status `UNDER CONSTRUCTION` → `OPERATIONAL` (or `FAILED`, not enforced, recreate after fixing data). UNIQUE needs a range index on exactly the same properties. Verified 6.0.2: both created (`PENDING` → `OPERATIONAL`); violations error with `unique constraint violation on node of type C` and `mandatory constraint violation: node with label C missing property n`. Relationship constraints exist (`… RELATIONSHIP …`) – syntax in the commands docs, not verified here.

---
## 5. Data types and storability ([datatypes](https://docs.falkordb.com/datatypes.md))

| Type | Notes | Storable as property? |
|---|---|---|
| Node / Relationship / Path | rel has exactly one type, always directed; path = alternating nodes/edges | **No** |
| String | Unicode | yes |
| Boolean | stored numeric internally; `1 = true` → false (typed compare) | yes |
| Integer | 64-bit signed | yes |
| Float | 64-bit double | yes |
| Point | lat/lon as two 32-bit floats; `point({latitude:,longitude:})` | yes |
| Null | 3-valued logic: `null = null` → null, `null IN [..]` → null | **No** (`SET p = NULL` removes) |
| Date / LocalTime / LocalDateTime / Duration | ISO 8601; `date('2025-09-15')`, `localtime('07:00:00')`, `localdatetime('2025-06-29T13:45:00')`, `duration('P3DT12H')`; component access `.year .month .day .hour .minute .second` (duration `.years .months .hours` …). **Verified storable** (typeOf → `Date`) and comparable with `< >`; `date + duration`, `localdatetime - duration` work. `datetime()`/`time()` don't exist on 6.0.2 | yes (FAQ lists Date/Time/DateTime/Duration) |
| Array/List | nested allowed in queries; storable only if no element is a graph entity or null | scalar arrays yes |
| Map | dot / bracket access, `+` merges (right wins), projections `n {.a, .b, k: expr}` | **No** |
| Vector (`vecf32`) | float32; used with vector index | yes (verified) |

Verified errors: `CREATE (:P {m:{a:1}})` and `CREATE (:P {l:[1,null]})` → `Property values can only be of primitive types or arrays of primitive types`. Use epoch-ms integers (`timestamp()`) when you need cheap, indexable time filtering.
Map projection on a null entity yields `null` (so `collect(DISTINCT o {.name})` after an unmatched OPTIONAL MATCH is `[]`); on a real node with missing props it returns `{id: NULL, …}` (verified). Hex/octal numeric literals unsupported ([support](https://docs.falkordb.com/cypher/cypher-support.md)). Nodes/relationships are not internally comparable.

---
## 6. Parameters, plan cache, EXPLAIN / PROFILE
- Parameters: prefix with `CYPHER`, reference as `$name`: `CYPHER name="Niccolò" birth_year=1469 MATCH (p:Person {name:$name, birth_year:$birth_year}) RETURN p` ([support](https://docs.falkordb.com/cypher/cypher-support.md)); client libraries provide native binding. Never concatenate user input ([cheat-sheet](https://docs.falkordb.com/cypher/cheat-sheet.md)). Parameter values may be lists/maps (verified: `CYPHER rows=[{id:'u2'},…] UNWIND $rows AS r …`).
- Plan cache (observed, **verified**): reply stats include `Cached execution: 0|1`; re-running the same query text with different parameter values reports `Cached execution: 1` → keep query text constant and vary params. (Cache details are not in the Cypher docs.)
- `GRAPH.EXPLAIN g "<q>"` – plan without running; `GRAPH.PROFILE g "<q>"` – runs and adds `Records produced` + `Execution time` per op; `GRAPH.RO_QUERY` – read-only. Example plans verified: `Node By Index Scan | (m:Mem)`, `Conditional Traverse | (m)->(x)`, `Filter`, `Node By Vector Index Scan`, `ProcedureCall | db.idx.…`.
- Use EXPLAIN to confirm index usage (see Index Scan vs label scan); PROFILE for timing ([range-index](https://docs.falkordb.com/cypher/indexing/range-index.md)). Default query timeout on this image: 1000 ms.
- Caution (unverified cause): on the dev container the query `MATCH (a:C) WHERE size([(a)-[:R]->() | 1]) = 0 RETURN a.n` was followed by a >60 s hang and a container restart (exit 137, OOMKilled=false). Not reproduced deliberately; prefer `WHERE NOT (a)-[:R]->()` (verified OK).

---
## 7. Support matrix, limitations, differences vs Neo4j

| Area | Status |
|---|---|
| Patterns, MATCH, OPTIONAL MATCH, WHERE/ORDER/SKIP/LIMIT, RETURN/WITH/UNWIND, CREATE/DELETE/SET/REMOVE/MERGE, UNION [ALL], CALL proc, CALL {}, FOREACH, LOAD CSV, CASE, list/pattern comprehensions, XOR | supported ([support](https://docs.falkordb.com/cypher/cypher-support.md), [index](https://docs.falkordb.com/cypher/index.md)) |
| DELETE | always DETACH (relationships auto-removed) |
| Label expressions `(n:A\|B)` | unsupported (verified) |
| Regex operator `=~` | documented unsupported; **works on 6.0.2** [CONFLICT] |
| Temporal arithmetic *functions*, `datetime()`, `time()` | missing (operators `+ -` on temporals work) |
| Hex/octal literals | unsupported |
| Schema-introspection queries (`SHOW …`) | unsupported; use `db.*` procedures/`labels()`/`type()` |
| `exists((n)-[]->())` | unsupported → pattern predicate |
| `count{}`/`EXISTS {}` subqueries | not documented; `count{}` parse-errors (verified) |
| Constraints | via `GRAPH.CONSTRAINT`, not Cypher DDL |
| Multiple graphs per query / USE | not documented |

Known limitations ([limitations](https://docs.falkordb.com/cypher/known-limitations.md)):
1. **Relationship uniqueness shortcut:** an unreferenced relationship alias in a pattern is only checked for existence. With two parallel edges `(a)-[:e]->(b)` ×2, `MATCH (a)-[e]->(b) RETURN COUNT(e)` = 2 but `RETURN COUNT(b)` = 1. Workaround: reference the alias (`WHERE ID(e) >= 0` or return `e.dummyval`).
2. `LIMIT` does not bound eager operations (CREATE/SET/DELETE/MERGE/aggregating projections).
3. Indexes don't serve `<>`.
4. Aggregates not allowed inside pattern comprehensions.
5. Vector queries don't combine with property filters (post-filter only).
6. `MATCH … ` var-length paths: relationship uniqueness only; verified nodes may repeat (`[u1,u3,u1,u2]`).

Differences vs Neo4j: Redis protocol (`GRAPH.QUERY`, no Bolt); `CYPHER k=v` param prefix; no label expressions; DDL index syntax `CREATE INDEX FOR (…) ON (…)` is Neo4j-like but vector/fulltext are procedure-backed (`db.idx.*`) with RediSearch syntax; no `GROUP BY` (implicit); `id()` unstable; maps/null/entities not storable; `shortestPath` endpoints must be pre-bound and accept no property filters; built-in `algo.*` instead of GDS; `list.*`, `string.*`, `vec.*` namespaces; no APOC.

---
## 8. COOKBOOK (copy-ready; "(adapted)" = not verbatim from docs; "✔ 6.0.2" = executed OK)

1. **Upsert node with timestamps** – `MERGE (p:Person {id:$id}) ON CREATE SET p.created = timestamp() ON MATCH SET p.last_seen = timestamp() RETURN p` ([merge](https://docs.falkordb.com/cypher/merge.md); pattern from [cheat-sheet](https://docs.falkordb.com/cypher/cheat-sheet.md)) (adapted) ✔ 6.0.2.
2. **Batch upsert from a list of maps** – `UNWIND $rows AS r MERGE (p:Person {id:r.id}) SET p += r RETURN count(p)` (adapted from [unwind](https://docs.falkordb.com/cypher/unwind.md)) ✔ 6.0.2 (pass rows as `CYPHER rows=[{…}] …` or client param).
3. **Batch edges between existing nodes** – `UNWIND $edges AS e MATCH (x:C {n:e.a}),(y:C {n:e.b}) MERGE (x)-[r:LINK]->(y) SET r.w = e.w` (adapted) ✔ 6.0.2.
4. **Safe relationship upsert (no duplicate endpoints)** – `MERGE (a {name:'Charlie Sheen'}) MERGE (m:Movie {name:'Wall Street'}) MERGE (a)-[r:ACTED_IN]->(m)` ([merge](https://docs.falkordb.com/cypher/merge.md)).
5. **Link only if both ends exist** – `MATCH (a {name:'A'}) MATCH (b:Movie {name:'B'}) MERGE (a)-[r:ACTED_IN]->(b)` ([merge](https://docs.falkordb.com/cypher/merge.md)).
6. **Conditional write (do-if-absent)** – `MATCH (h:HOTEL) OPTIONAL MATCH (h)-[b:BUYS_FROM]->(:BAKERY) FOREACH(_ IN CASE WHEN b IS NULL THEN [1] ELSE [] END | MERGE (h)-[b2:BUYS_FROM]->(s:SUPPLIER {supplies_bread:true}) SET b2.direct=false)` ([foreach](https://docs.falkordb.com/cypher/foreach.md)); simplified form `MATCH (a:Person {id:'u2'}) FOREACH(x IN CASE WHEN a.flag IS NULL THEN [1] ELSE [] END | SET a.flag=true)` (adapted) ✔ 6.0.2.
7. **Mark path nodes / bulk flag** – `MATCH p=(a:City)-[:ROAD*..5]->(b:City) FOREACH (n IN nodes(p) | SET n.part_of_path = true)` ([cheat-sheet](https://docs.falkordb.com/cypher/cheat-sheet.md)).
8. **Variable-length traversal (1–3 hops)** – `MATCH p=(a:Person {id:$id})-[:KNOWS*1..3]->(b) RETURN [n IN nodes(p) | n.id] AS ids, length(p) ORDER BY length(p)` (adapted from [match](https://docs.falkordb.com/cypher/match.md)) ✔ 6.0.2.
9. **Shortest path with explainable result** – `MATCH (a:City{name:'A'}),(g:City{name:'G'}) WITH shortestPath((a)-[*]->(g)) AS p RETURN length(p), [n IN nodes(p) | n.name] AS pathNodes` ([functions](https://docs.falkordb.com/cypher/functions.md)) ✔ 6.0.2 (adapted with `:KNOWS`).
10. **All shortest paths** – `MATCH (a:City{name:'A'}),(g:City{name:'G'}) WITH a,g MATCH p=allShortestPaths((a)-[*]->(g)) RETURN length(p), [n IN nodes(p) | n.name]` ([functions](https://docs.falkordb.com/cypher/functions.md)); endpoints must be bound via the `WITH` ✔ 6.0.2.
11. **Weighted shortest path** – `MATCH (a:City {name:'A'}), (g:City {name:'G'}) CALL algo.SPpaths({sourceNode:a, targetNode:g, relTypes:['ROAD'], weightProp:'dist', pathCount:1}) YIELD path, pathWeight RETURN path, pathWeight` ([cheat-sheet](https://docs.falkordb.com/cypher/cheat-sheet.md)) ✔ 6.0.2.
12. **Return named path for explainability** – `MATCH p=(c:Actor {name:'Charlie Sheen'})-[:PLAYED_WITH*1..3]->(:Actor) RETURN nodes(p) AS actors, relationships(p) AS via` ([match](https://docs.falkordb.com/cypher/match.md)) (adapted: added `relationships`). Path filtering: `MATCH p=()-[*]->() WHERE all(edge IN relationships(p) WHERE edge.weight < 3) RETURN p` ([functions](https://docs.falkordb.com/cypher/functions.md)).
13. **Vector top-k (nearest first)** – `CALL db.idx.vector.queryNodes('Mem','emb',5,vecf32($q)) YIELD node, score RETURN node.id, score ORDER BY score ASC` (adapted; **ASC** per verified score semantics, docs example uses DESC [CONFLICT]) ✔ 6.0.2.
14. **Hybrid vector + graph retrieval** – `CALL db.idx.vector.queryNodes('Mem','emb',20,vecf32($q)) YIELD node, score WHERE node.agent = $agent MATCH (node)<-[:WROTE]-(who) RETURN node.id, who, score ORDER BY score ASC LIMIT 5` (adapted) – YIELD/WHERE/MATCH chaining ✔ 6.0.2 (filter applies *after* top-k; over-fetch k).
15. **Full-text lookup (+ prefix, boolean, fuzzy)** – `CALL db.idx.fulltext.queryNodes('Mem','dar*') YIELD node, score RETURN node.id, score ORDER BY score DESC`; `'dark -chocolate'`; `'chocolate|hackathon'`; fuzzy `'%dari%'` ([fulltext](https://docs.falkordb.com/cypher/indexing/fulltext-index.md)) ✔ 6.0.2.
16. **Full-text then property filter** – `CALL db.idx.fulltext.queryNodes('Movie','Book') YIELD node AS m WHERE m.genre='Adventure' RETURN m ORDER BY m.rating` ([fulltext](https://docs.falkordb.com/cypher/indexing/fulltext-index.md)).
17. **Temporal validity window (epoch-ms ints)** – `MATCH (m:Mem) WHERE m.valid_from <= $t AND m.valid_to > $t RETURN m.id` (adapted; add `CREATE INDEX FOR (m:Mem) ON (m.valid_from)`) ✔ 6.0.2. Native types also work: `WHERE p.d >= date('2025-01-01')`, `localdatetime() - duration('PT30M')`.
18. **Close a validity window (expire old fact, insert new)** – `MATCH (m:Mem {id:$id}) WHERE m.valid_to > timestamp() SET m.valid_to = timestamp()` then `CREATE (:Mem {id:$id2, valid_from: timestamp(), valid_to: 9223372036854775807})` (adapted).
19. **Top-k aggregation** – `MATCH (m:Mem) WITH m.agent AS agent, count(*) AS c RETURN agent, c ORDER BY c DESC LIMIT 3` (adapted) ✔ 6.0.2; per-group sample `collect(m.id)[0..1]` ✔.
20. **Per-row subquery aggregation** – `MATCH (item:Item) CALL { WITH item MATCH (item)-[s:SOLD_TO]->(:Customer) RETURN count(s) AS sales } RETURN item.name, sales` ([call](https://docs.falkordb.com/cypher/call.md)) ✔ 6.0.2 (adapted with `:KNOWS`).
21. **Anti-join / absence check** – `MATCH (a:Person) WHERE NOT (a)-[:KNOWS]->(:Person {id:'u1'}) RETURN a.id` ([where](https://docs.falkordb.com/cypher/where.md)) ✔ 6.0.2; leaf nodes `MATCH (a:C) WHERE NOT (a)-[:R]->() RETURN a.n` ✔.
22. **Existence of relation (semi-join)** – `MATCH (p:Person), (c:Company) WHERE (p)-[:WORKS_AT]->(c) AND NOT (p)-[:FOUNDED]->(c) RETURN p, c` ([cheat-sheet](https://docs.falkordb.com/cypher/cheat-sheet.md)).
23. **Optional enrichment** – `MATCH (p:Person) OPTIONAL MATCH (p)-[w:WORKS_AT]->(c:Company) WHERE w.start_date > 2016 RETURN p, w, c` ([optional-match](https://docs.falkordb.com/cypher/optional-match.md)).
24. **List comprehension** – `MATCH p=()-[*]->() RETURN [node IN nodes(p) WHERE node.rank > 10 | node.name]` ([functions](https://docs.falkordb.com/cypher/functions.md)).
25. **Pattern comprehension** – `MATCH (n:Person) RETURN n.name, [(n)-[e:FRIEND_OF]->(f:Person) WHERE e.since < 2010 | f.age]` ([functions](https://docs.falkordb.com/cypher/functions.md)); `MATCH (a:Person) RETURN a.id, [(a)-[r:KNOWS]->(b) | b.id] AS friends` ✔ 6.0.2.
26. **Conditional value** – `RETURN CASE WHEN n.age < 18 THEN '0-18' WHEN n.age < 30 THEN '18-30' ELSE '30+' END` ([functions](https://docs.falkordb.com/cypher/functions.md)); `coalesce(a.nope,'dflt')` ✔.
27. **Pagination** – `MATCH (p:Person) RETURN p ORDER BY p.name SKIP 100 LIMIT 100` ([skip](https://docs.falkordb.com/cypher/skip.md)).
28. **Deletion** – node+edges `MATCH (p:Person {name:'Jim'}) DELETE p`; edge only `MATCH (:Person {name:'Jim'})-[r:FRIENDS]->() DELETE r`; conditional `MATCH (p:Person) WHERE p.age < 18 DELETE p`; wipe `MATCH (n) DETACH DELETE n` ([delete](https://docs.falkordb.com/cypher/delete.md)).
29. **Property surgery** – replace `SET n = {a:1}`; merge `SET n += {a:1}`; drop `REMOVE n.score` / `SET n.score = NULL`; label `REMOVE n:Admin` ([set](https://docs.falkordb.com/cypher/set.md), [remove](https://docs.falkordb.com/cypher/remove.md)).
30. **Constraint-backed idempotent id** – `CREATE INDEX FOR (m:Mem) ON (m.id)` + `GRAPH.CONSTRAINT CREATE g UNIQUE NODE Mem PROPERTIES 1 id` + `GRAPH.CONSTRAINT CREATE g MANDATORY NODE Mem PROPERTIES 1 id`, then `MERGE (m:Mem {id:$id})` ✔ 6.0.2 (constraints operational; violations error).
31. **Graph introspection** – `CALL db.labels()`, `CALL db.indexes()`, `CALL db.meta.stats()`, `CALL dbms.procedures() YIELD name, mode` ([procedures](https://docs.falkordb.com/cypher/procedures.md)) ✔ 6.0.2.
32. **Count every parallel edge correctly** – `MATCH (a)-[e]->(b) WHERE ID(e) >= 0 RETURN COUNT(b)` ([limitations](https://docs.falkordb.com/cypher/known-limitations.md)).
33. **CSV import** – `LOAD CSV WITH HEADERS FROM 'file://acted_in.csv' AS row MATCH (a:Actor {name: row['actor']}) MERGE (m:Movie {title: row['movie']}) MERGE (a)-[:ACTED_IN]->(m)` ([load-csv](https://docs.falkordb.com/cypher/load-csv.md)).

**Pitfalls checklist for the agent-memory build:** (a) sort vector scores ascending; (b) over-fetch k when post-filtering; (c) store time as epoch-ms ints (or native temporal types) – never maps/null/nested lists as properties (serialize with `toJSON()` to a string if needed); (d) `MERGE` per entity, relationship in its own clause; (e) pass data via `CYPHER`/client params, keep text constant for plan-cache hits; (f) `LIMIT` won't cap writes; (g) don't rely on CCH, `datetime()`, `vecf64()` on 6.0.2; (h) `id()` values are not stable – use your own `id` property + UNIQUE constraint.
