# E — FalkorDB Ecosystem Reference (agentic memory, MCP, GenAI tools, integrations, Browser)

Scope: Graph Hacks, Track 02 "Agent Memory and Coordination" on FalkorDB 6.0. All claims link to the docs page they come from. "Not documented" means the page does not say. Items marked **[Inference]** are my own reasoning, not docs. Snippets are copied verbatim from the pages (the docs mask some `Bearer` tokens as `Bearer ***`; use a real token there). 53 pages read.

---

## 1. Agentic memory frameworks

Docs overview: all three frameworks can share one FalkorDB instance using different graph names ([index FAQ](https://docs.falkordb.com/agentic-memory/index)). Most need an LLM provider for entity extraction and embeddings ([index FAQ](https://docs.falkordb.com/agentic-memory/index)).

| | Graphiti | Graphiti MCP Server | Cognee | Mem0 (mem0-falkordb) |
|---|---|---|---|---|
| Install | `pip install graphiti-core[falkordb]` | Docker (compose or `zepai/knowledge-graph-mcp:standalone`) | `pip install "cognee>=1.2,<2.0"` + `pip install cognee-community-hybrid-adapter-falkor` | `pip install mem0ai` + `pip install mem0-falkordb` |
| Python | 3.10+ | 3.10+ only for standalone run | 3.11–3.13 (not 3.10/3.14) | 3.10+ |
| Tenancy | `graph_name=` per user/agent | `group_id` (`GRAPHITI_GROUP_ID`); graph mapping not documented | not documented (dataset handlers, see below) | one graph per `user_id`: `{database}_{user_id}` |
| LLM | OpenAI default; pluggable client | OpenAI default `gpt-4o-mini`; Anthropic/Gemini/Groq/Azure | `LLM_API_KEY`, `gpt-4o-mini` in example | OpenAI `gpt-4o-mini` in example |
| Maturity signal | Standard integration page | Index labels it *(Experimental)* | Adapter is **community-maintained** | Plugin patches Mem0 at runtime |

### 1.1 Graphiti — temporal knowledge graph ([page](https://docs.falkordb.com/agentic-memory/graphiti))
- Prereqs: Python 3.10+, FalkorDB (Cloud or self-hosted), OpenAI API key.
- Data model: **episodes** (text/message/JSON with `reference_time`) are processed into entities and relationships; temporal queries via `reference_time` ([page](https://docs.falkordb.com/agentic-memory/graphiti)). Edge/node property schema is **not documented** on this page (the MCP page gives one, §1.2).
- Connect (verbatim from page):
```python
graphiti = Graphiti(
    uri="falkor://localhost:6379",  # Your FalkorDB connection string
    # For FalkorDB Cloud:
    # uri="falkor://your-instance.falkordb.cloud:6379",
    # username="default",
    # password="your-password"
)
await graphiti.build_indices_and_constraints()   # once
await graphiti.add_episode(name=..., episode_body=..., episode_type=EpisodeType.text, reference_time=datetime(2024, 3, 15), source_description="Conference notes")
results = await graphiti.search(query="...", num_results=5)
```
- Tenant per graph (verbatim): `Graphiti(uri="falkor://localhost:6379", graph_name="user1_memory")`; "Each graph is completely isolated, leveraging FalkorDB's native multi-graph support" ([FAQ](https://docs.falkordb.com/agentic-memory/graphiti)).
- Also documented: `retrieve_nodes`, `retrieve_episodes`, `search(..., reference_time=...)`, custom `OpenAIClient` LLM client. Best practices: batch episodes, always set reference times, build indices once, reuse instances.
- **Caveat [Inference]:** the `uri=`/`graph_name=` constructor shown here may not match current graphiti-core releases (which, as far as I know, take a FalkorDB driver object). Verify against the Graphiti source before building on it; the docs page cannot confirm either way.

### 1.2 Graphiti MCP Server ([page](https://docs.falkordb.com/agentic-memory/graphiti-mcp-server))
- Run (combined FalkorDB+MCP image, recommended): download `https://raw.githubusercontent.com/getzep/graphiti/main/mcp_server/docker/docker-compose.yml`, create `.env` with:
```env
OPENAI_API_KEY=your-openai-api-key
FALKORDB_PASSWORD=
GRAPHITI_GROUP_ID=main
```
then `docker-compose up -d`. Endpoints: FalkorDB `localhost:6379`, Browser `http://localhost:3000`, MCP `http://localhost:8000/mcp/`, health `http://localhost:8000/health`. Separate-container variant uses `docker-compose-falkordb.yml` with `FALKORDB_URI=redis://falkordb:6379`, `FALKORDB_DATABASE=default_db`.
- Env vars: `OPENAI_API_KEY` (or another provider key), `FALKORDB_URI` (default `redis://localhost:6379`), `FALKORDB_PASSWORD`, `FALKORDB_DATABASE` (default `default_db`), `SEMAPHORE_LIMIT` (episode concurrency, default `10`), `BROWSER` (default `1`). Rate-limit guidance: OpenAI Tier 1 → 1-2, Tier 2 → 5-8, Tier 3 → 10-15, Tier 4 → 20-50, Anthropic → 5-8.
- Defaults: HTTP transport at `/mcp/`, LLM OpenAI `gpt-4o-mini`, embedder `text-embedding-3-small`. LLMs: OpenAI, Anthropic, Gemini, Groq, Azure OpenAI. Embedders: OpenAI, Voyage, Sentence Transformers, Gemini. stdio is possible only from a cloned repo (see Graphiti README).
- Client config (Claude Desktop, verbatim):
```json
{
  "mcpServers": {
    "graphiti-memory": {
      "transport": "http",
      "url": "http://localhost:8000/mcp/"
    }
  }
}
```
- **Tools:** `add_episode`, `search_nodes`, `search_facts`, `delete_entity_edge`, `delete_episode`, `get_entity_edge`, `get_episodes`, `clear_graph`.
- **Entity types (built-in):** Preference, Requirement, Procedure, Location, Event, Organization, Document, Topic, Object — customisable in `config.yaml` when run from source. (`Procedure` is a ready-made procedural-memory type.)
- **Schema the page documents:** nodes `Entity` (`name`, `entity_type`, `summary`) and `Episode` (`name`, `content`, `timestamp`, `source`); relationships `RELATES_TO`, `MENTIONED_IN`, `OCCURRED_AFTER`; "All data is stored in a graph named `graphiti_memory`". Note this conflicts with the `FALKORDB_DATABASE=default_db` env var on the same page — the page does not reconcile them, so inspect the live graph with Browser (`MATCH (n) RETURN n LIMIT 25`) before trusting it.
- Not exposed: REST endpoints — only `/mcp/` and `/health`; for programmatic access use an MCP client library or query FalkorDB directly ([Advanced Usage](https://docs.falkordb.com/agentic-memory/graphiti-mcp-server)).
- Persistence: default containers lose data on restart; use compose volumes ([FAQ](https://docs.falkordb.com/agentic-memory/graphiti-mcp-server)).

### 1.3 Cognee ([page](https://docs.falkordb.com/agentic-memory/cognee))
- FalkorDB via a **community adapter** `cognee-community-hybrid-adapter-falkor` (needs `cognee >= 1.0.3`, `falkordb >= 1.0.9`); FalkorDB is used as **both** graph and vector store ("hybrid"). Provider name is `"falkor"` (not `"falkordb"`); import `register` from `cognee_community_hybrid_adapter_falkor` **before** any `config.set_*` call.
- Config (verbatim):
```python
config.set_vector_db_config({
    "vector_db_provider": "falkor",
    "vector_db_url": os.getenv("GRAPH_DB_URL", "localhost"),
    "vector_db_port": int(os.getenv("GRAPH_DB_PORT", "6379")),
})
config.set_graph_db_config({
    "graph_database_provider": "falkor",
    "graph_database_url": os.getenv("GRAPH_DB_URL", "localhost"),
    "graph_database_port": int(os.getenv("GRAPH_DB_PORT", "6379")),
})
```
- Env: `GRAPH_DB_URL`, `GRAPH_DB_PORT`, `GRAPH_DATASET_DATABASE_HANDLER="falkor_graph_local"`, `VECTOR_DATASET_DATABASE_HANDLER="falkor_vector_local"`, `LLM_API_KEY`. The handler vars "tell Cognee's dataset system to use the FalkorDB handlers"; the page does **not** say whether this yields graph-per-dataset/tenant.
- Flow: `add(text)` → `cognify()` (LLM entity/relation extraction) → `search(query_type=SearchType.GRAPH_COMPLETION, ...)`. Search types: `GRAPH_COMPLETION`, `CHUNKS`, `RAG_COMPLETION`, `SUMMARIES`, `TEMPORAL`, `CYPHER` (raw Cypher), `NATURAL_LANGUAGE`, `GRAPH_COMPLETION_COT`, `HYBRID_COMPLETION`. Reset with `prune.prune_data()` / `prune.prune_system(metadata=True)`.
- Also needs a relational DB for metadata (`sqlite` default, or `postgres`). Schema FalkorDB receives: not documented.
- Run FalkorDB: `docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest`.

### 1.4 Mem0 ([page](https://docs.falkordb.com/agentic-memory/mem0))
- `mem0-falkordb` ([repo](https://github.com/FalkorDB/mem0-falkordb)) "adds FalkorDB as a graph store backend for Mem0 without modifying any Mem0 source code" by runtime patching — call `register()` before creating `Memory`.
- Quick start (verbatim):
```python
from mem0_falkordb import register
register()

from mem0 import Memory

config = {
    "graph_store": {
        "provider": "falkordb",
        "config": {
            "host": "localhost",
            "port": 6379,
            "database": "mem0",
        },
    },
    "llm": {
        "provider": "openai",
        "config": {"model": "gpt-4o-mini"},
    },
}

m = Memory.from_config(config)
m.add("I love pizza", user_id="alice")
results = m.search("what does alice like?", user_id="alice")
```
- Config table: `host` (localhost), `port` (6379), `database` (`mem0`, "Graph name prefix (each user gets `{database}_{user_id}`)"), `username`, `password`, `base_label` (True, "Use `__Entity__` base label").
- **Tenancy:** automatic graph per user (`mem0_alice`, `mem0_bob`): no `user_id` filter in Cypher; `delete_all(user_id=...)` "simply drops the user's graph". This is the cleanest documented graph-per-tenant pattern.
- API surface shown: `add`, `search`, `get_all`, `delete(memory_id=, user_id=)`, `delete_all`, `history(memory_id=)` (entries have `version`, `changed_at`). Conflict resolution on updates is done by Mem0 (LLM).
- Schema beyond the `__Entity__` base label: not documented. Demo: `git clone https://github.com/FalkorDB/mem0-falkordb.git` then `uv run python demo.py` (needs `OPENAI_API_KEY`).

---

## 2. FalkorDB MCP Server ([index](https://docs.falkordb.com/genai-tools/mcpserver), [quickstart](https://docs.falkordb.com/genai-tools/mcpserver/quickstart), [configuration](https://docs.falkordb.com/genai-tools/mcpserver/configuration), [docker](https://docs.falkordb.com/genai-tools/mcpserver/docker))

- **What:** generic MCP server over FalkorDB (npm `@falkordb/mcpserver`, Docker `falkordb/mcpserver`, [repo](https://github.com/FalkorDB/FalkorDB-MCPServer)). Not a memory framework: it exposes raw graph access. Needs Node.js 18+.
- **Features:** query graphs with OpenCypher (read-only supported), create/manage nodes and relationships, list graphs, delete graphs, replica support. The only tool name the docs give is `query_graph` (has a `readOnly` parameter that runs `GRAPH.RO_QUERY`). Other tool names: **not documented**.
- **Env vars** (verbatim from configuration page):
```bash
FALKORDB_HOST=localhost
FALKORDB_PORT=6379
FALKORDB_USERNAME=          # Optional
FALKORDB_PASSWORD=          # Optional
FALKORDB_DEFAULT_READONLY=false  # Set to 'true' for read-only mode
MCP_TRANSPORT=stdio         # 'stdio' (default) or 'http'
MCP_PORT=3000              # Port for HTTP transport
MCP_API_KEY=               # Optional API key for HTTP transport
ENABLE_FILE_LOGGING=false
```
- **Transports:** `stdio` (default, for Claude Desktop) or `http` (MCP Streamable HTTP; `Authorization: Bearer <key>` enforced when `MCP_API_KEY` is set). The page's meta description says "stdio/SSE" but the body documents only stdio and http.
- **Read-only mode:** `FALKORDB_DEFAULT_READONLY=true` ("default" suggests per-call override via `readOnly`; the interaction is not spelled out). Documented uses: replicas, production safety, dashboards, multi-tenant read-only access.
- **Per-agent/tenant isolation:** the server takes one host/credential set, so the documented route is *multiple server entries* (e.g. `falkordb-dev`, `falkordb-prod-replica`) with different env ([configuration](https://docs.falkordb.com/genai-tools/mcpserver/configuration)). Binding a server to one graph is **not documented**; combine with a FalkorDB ACL user if you need hard limits (ACLs are covered in other parts).
- **Run:**
```json
{
  "mcpServers": {
    "falkordb": {
      "command": "npx",
      "args": ["-y", "@falkordb/mcpserver@latest"],
      "env": {
        "FALKORDB_HOST": "localhost",
        "FALKORDB_PORT": "6379",
        "FALKORDB_USERNAME": "",
        "FALKORDB_PASSWORD": ""
      }
    }
  }
}
```
  HTTP: `MCP_TRANSPORT=http MCP_PORT=3005 FALKORDB_HOST=localhost FALKORDB_PORT=6379 npx -y @falkordb/mcpserver`. Docker: `docker run -p 3000:3000 -e FALKORDB_HOST=host.docker.internal -e FALKORDB_PORT=6379 -e MCP_API_KEY=your-secret-key falkordb/mcpserver:latest` (tags `latest`, `edge`, pinned e.g. `1.0.0`; exposes 3000). Compose: clone repo, `cp .env.example .env`, `docker compose up -d`.
- **How an agent would use it:** natural-language prompts ("Show me all people who know each other", "Create a new person named Alice who knows Bob", "List all available graphs", "Run a read-only query on the replica instance") are turned into Cypher and run via the tools ([quickstart](https://docs.falkordb.com/genai-tools/mcpserver/quickstart)). **[Inference]** For Track 02 it works as a *debug/observer channel* (read-only second server for a "reviewer" agent) rather than the memory write path, since writes would be free-form LLM Cypher.

---

## 3. GenAI integrations (what each gives you + minimal setup)

Index: [genai-tools](https://docs.falkordb.com/genai-tools).

| Tool | Gives you | Minimal setup (from docs) |
|---|---|---|
| **LangChain (Python)** [page](https://docs.falkordb.com/genai-tools/langchain) | `FalkorDBGraph` (schema introspection, `GraphDocument` ingest), `FalkorDBVector` (vector index store; metadata filter, MMR, hybrid vector+full-text), `FalkorDBQAChain` (NL→Cypher), `FalkorDBSaver` (LangGraph checkpointer), **`FalkorDBChatMessageHistory`** | `pip install langchain-falkordb` |
| **LangChain (JS/TS)** | `FalkorDBGraph.initialize({host, port, graph})`, `GraphCypherQAChain` | `npm install @falkordb/langchain-ts falkordb langchain @langchain/openai` |
| **LangGraph** [page](https://docs.falkordb.com/genai-tools/langgraph) | Stateful multi-actor workflows; FalkorDB-backed checkpointing so "threads survive restarts and can be shared between processes" | `pip install langgraph "langchain-falkordb[langgraph]" langchain-openai` |
| **LlamaIndex** [page](https://docs.falkordb.com/genai-tools/llamaindex) | `FalkorDBGraphStore` + `KnowledgeGraphIndex` (triplet extraction, hybrid embedding retrieval, `index.insert(doc)` incremental) | `pip install llama-index llama-index-graph-stores-falkordb` |
| **AG2 (AutoGen)** [page](https://docs.falkordb.com/genai-tools/ag2) | `FalkorGraphQueryEngine` + `FalkorGraphRagCapability.attach(agent, query_engine)`; several agents can attach the same engine (group chat) | `pip install -U ag2[openai,graph-rag-falkor-db]` |
| **GraphRAG SDK** [page](https://docs.falkordb.com/genai-tools/graphrag-sdk) | Document → KG ingestion, cited hybrid retrieval, incremental updates; hosted GraphRAG Server. Owned by another researcher part; full docs at [/graphrag](https://docs.falkordb.com/graphrag) | `pip install "graphrag-sdk[litellm,pdf]"` |
| **AWS GraphRAG Toolkit** [page](https://docs.falkordb.com/genai-tools/graphrag-toolkit) | FalkorDB as lexical-graph store; semantic-guided search. **Traversal-based search not supported** | `pip install https://github.com/awslabs/graphrag-toolkit/archive/refs/tags/v3.13.3.zip#subdirectory=lexical-graph-contrib/falkordb`; `GraphStoreFactory.register(FalkorDBGraphStoreFactory)`; `GraphStoreFactory.for_graph_store('falkordb://')` |
| **QueryWeaver** [page](https://docs.falkordb.com/genai-tools/queryweaver) | Text2SQL for PostgreSQL/MySQL/Snowflake using schema stored as a FalkorDB graph; REST + built-in MCP (`list_databases`, `connect_database`, `database_schema`, `query_database`) | `docker run -p 5000:5000 -it falkordb/queryweaver` (+ one LLM key, e.g. `OPENAI_API_KEY`) |
| **Code-Graph** [page](https://docs.falkordb.com/genai-tools/code-graph) | Index Python/Java/C# repos into a graph; React UI, GraphRAG chat, `cgraph` CLI (JSON output), git-history analysis | `pip install falkordb-code-graph`; `cgraph ensure-db`; `cgraph index . --ignore node_modules --ignore .git --ignore venv` |
| **Graphify** [page](https://docs.falkordb.com/genai-tools/graphify) | Turn code/docs/PDFs/notes into a KG and push to FalkorDB (graph `graphify` by default); `MERGE`-based, so re-push is additive and deletions are not propagated; supports `--mcp` mode | `pip install "graphifyy[falkordb]"`; `graphify install`; `/graphify ./my-project --falkordb-push falkordb://localhost:6379` |
| **n8n** [page](https://docs.falkordb.com/integration/n8n) | Community nodes `FalkorDB GraphRAG` (pipeline), `FalkorDB GraphRAG Tool` (AI-Agent tool) and credential `FalkorDB GraphRAG Server API`; talks to a **GraphRAG-Server**, not directly to FalkorDB | `npm install @falkordb/n8n-nodes-graphrag` |

Memory-relevant details:
- `FalkorDBChatMessageHistory`: "Each session is stored in its own graph named after the `session_id`, so histories are isolated per session and survive reconnects" (verbatim snippet):
```python
history = FalkorDBChatMessageHistory(
    session_id="user-42",
    host="localhost",
    port=6379,
)
history.add_user_message("Hello!")
history.add_ai_message("Hi! How can I help?")
print(history.messages)
```
- `FalkorDBSaver` (verbatim): `from langchain_falkordb.checkpoint import FalkorDBSaver`; `memory = FalkorDBSaver(host="localhost", port=6379)`; `app = workflow.compile(checkpointer=memory)`; `config = {"configurable": {"thread_id": "user_123"}}`. This is the closest documented thing to "shared state + handoff between agents": two processes can resume the same `thread_id`. Checkpoint graph layout: not documented.
- `FalkorDBQAChain` requires `allow_dangerous_requests=True` because it runs LLM-generated Cypher; the page advises narrowly-scoped credentials.
- LangChain Python connect: `FalkorDBGraph("movies", host="localhost", port=6379, username=None, password=None, ssl=False)`; `FalkorDBVector.from_documents(docs, embeddings, host=..., port=..., database="company_knowledge")`.
- LlamaIndex connect: `FalkorDBGraphStore(hostname=..., port=..., username=..., password=..., database="my_knowledge_graph")` — `database` is the graph name.
- AG2 connect: `FalkorGraphQueryEngine(name="company_knowledge", host="localhost", port=6379)`; `query_engine.init_db(input_doc=...)`. AG2 page claims "Multi-Tenancy: Isolate knowledge graphs for different projects or users" (mechanism = `name`).

---

## 4. Integrations ([index](https://docs.falkordb.com/integration))

- **REST API (via Browser)** [page](https://docs.falkordb.com/integration/rest): Browser v1.4.6 REST, JWT bearer auth. Needs `ENCRYPTION_KEY` (`openssl rand -hex 32`) in `.env.local`. Flow: `POST /api/auth/tokens/credentials` with `{"username":"default","password":"","host":"localhost","port":"6379","tls":"false"}` (optional `name`, `expiresAt`, `ttlSeconds` max 31622400) → `{"token": "<JWT_TOKEN>"}`. Endpoints: `GET /api/status`; `GET /api/graph` (list); `GET /api/graph/{graph}?query=...&timeout=30000` (**Server-Sent Events**, send `Accept: text/event-stream`); `POST/PATCH/DELETE /api/graph/{graph}` (create/rename via `sourceName`/delete); `GET .../explain`, `.../profile`, `.../info?type=(label)`, `.../count`, `.../export`; `PATCH .../duplicate?sourceName=`; node/edge: `GET/DELETE /api/graph/{graph}/{node}`, `POST/DELETE .../label`, `POST/DELETE .../{key}` (`type=true` node, `false` relationship); config `GET/POST /api/graph/config[/{config}]`; users `GET/POST/DELETE /api/user`, `PATCH /api/user/{user}?role=`; tokens `GET /api/auth/tokens`, `GET/DELETE /api/auth/tokens/{tokenId}`. Roles: `Admin`, `Read-Write`, `Read-Only`. Cypher parameter passing in the query endpoint: not documented.
- **Bolt (experimental)** [page](https://docs.falkordb.com/integration/bolt-support): "not meant to be used in production". Verbatim run: `docker run -p 6379:6379 -p 7687:7687 -p 3000:3000 -it -e REDIS_ARGS="--requirepass falkordb" -e FALKORDB_ARGS="BOLT_PORT 7687" --rm falkordb/falkordb:latest`; client `GraphDatabase.driver("bolt://localhost:7687", auth=("falkordb", ""))` with `driver.execute_query("UNWIND range(1, $n) AS i RETURN i", n=10, database_="mygraph")` — `database_` selects the graph.
- **Kafka Connect sink** [page](https://docs.falkordb.com/integration/kafka-connect): `connector.class=com.falkordb.FalkorDBSinkConnector`, `topics=falkordb-topic`, `falkor.url=redis://localhost:6379`, String converters, `value.converter.schemas.enable=false`. Message = JSON array of `{"graphName":"falkordb","command":"GRAPH_QUERY","cypherCommand":"CREATE (p:Person {name: $name_param, ...}) RETURN p","parameters":{...}}`; one message can target multiple graphs. **[Inference]** an append-only event/audit feed of agent actions into per-tenant graphs.
- **Apache Jena (SPARQL)** [page](https://docs.falkordb.com/integration/jena): `com.falkordb:jena-falkordb-adapter:0.2.0`. The page's Java snippet is explicitly a placeholder (`FalkorDBJenaFactory.createModel("http://localhost:7474")`; "see Main.java"), so treat the API as undocumented here.
- **Spring Data FalkorDB** [page](https://docs.falkordb.com/integration/spring-data-falkordb): `org.springframework.data:spring-data-falkordb:1.0.8` + `com.falkordb:jfalkordb:0.8.0`; `@Node`, `@Relationship`, `@Id`, `@Property`, `@Interned` (uses `intern()` for low-cardinality strings), `FalkorDBRepository<T, ID>`, derived queries (`findByAgeGreaterThan`), `@Query` with Cypher, `@EnableFalkorDBRepositories`, transaction manager. Client: `FalkorDB.driver("localhost", 6379)` + `new DefaultFalkorDBClient(driver, "social")` (graph name fixed per client).
- **Snowflake Native App** [page](https://docs.falkordb.com/integration/snowflake): runs FalkorDB in Snowpark Container Services. `CALL <app>.app_public.start_app('FALKORDB_POOL','FALKORDB_WH')`; load via `load_csv('my_graph', '<LOAD CSV Cypher>')` from a table bound to `consumer_data_table`; query via `graph_query('my_graph','MATCH ...')`; results can be written back; includes Browser and a Cortex Agent with tools `list_graphs`, `run_cypher`, `load_csv`, `text_to_cypher`. Not relevant to Track 02 beyond name-dropping.
- **PyTorch Geometric** [page](https://docs.falkordb.com/integration/pyg): `pip install falkordb-pyg`; `feature_store, graph_store = get_remote_backend(host="localhost", port=6379, graph_name="papers")`, then `NeighborLoader(data=(feature_store, graph_store), ...)`. Lazy, cached loading with automatic ID remapping.
- **Bulk loader** [page](https://docs.falkordb.com/integration/bulk-loader): `pip install falkordb-bulk-loader`; `falkordb-bulk-insert SocialGraph -n Person.csv -r KNOWS.csv` (label/type from filename; `--server-url redis://host:6379`; `-d` enforces `name:TYPE` headers such as `:ID(User),name:STRING,rank:INT`; `-i Label:Property` range index, `-f` full-text). `falkordb-bulk-update SocialGraph --csv User.csv --query "MERGE (:User {id: row[0], name: row[1], rank: row[2]})"` commits incrementally. Uses `GRAPH.BULK`.

---

## 5. FalkorDB Browser — demo-video material

Overview: [Browser](https://docs.falkordb.com/browser), UI index [ui](https://docs.falkordb.com/browser/ui). Port 3000 in the Docker image (Browser listed as port 3000 in [Bolt page](https://docs.falkordb.com/integration/bolt-support)).

| Feature | What to show | Source |
|---|---|---|
| Login | Manual host/port/user/pass/TLS/CA, or URL `falkor[s]://[[username][:password]@][host][:port][/db-number]` | [login](https://docs.falkordb.com/browser/ui/login) |
| Graph selector + multi-graph tabs | Up to 4–10 tabs (default 8); each tab keeps graph, query, view, viewport, selection, chat. Open one tab per tenant graph to show isolation | [tabs](https://docs.falkordb.com/browser/ui/graph-tabs), [graph page](https://docs.falkordb.com/browser/ui/graph-page) |
| Graph canvas | Pan/zoom, Force/Tree/Radial layouts, directions, pin, dim, animation, per-label/per-relationship visibility toggles, in-canvas search | [canvas](https://docs.falkordb.com/browser/ui/graph-canvas), [toolbar](https://docs.falkordb.com/browser/ui/toolbar-actions) |
| Style panel | Colour (15 presets + hex) and size per label/relationship type, stored in the browser. Colour episodic/semantic/procedural labels differently | [style](https://docs.falkordb.com/browser/ui/style-panel) |
| Graph Info | Node/edge counts, optional memory usage, labels, rel types, property keys; click to run `MATCH (n:Label) RETURN n` | [info](https://docs.falkordb.com/browser/ui/graph-info-panel) |
| Query editor | Monaco, live openCypher syntax validation, autocomplete (labels, rel types, properties, UDFs), "Fix with AI", Cmd/Ctrl+Enter | [editor](https://docs.falkordb.com/browser/ui/query-editor) |
| Query history | Stored in localStorage; search, filter by graph, per-query Edit/Profile/Metadata/Explain tabs | [history](https://docs.falkordb.com/browser/ui/query-history) |
| Table view + CSV export | Tabular results; `<graph>_table_export.csv` | [table](https://docs.falkordb.com/browser/ui/table-view) |
| Metadata / Profile / Explain | Nested execution plan trees (profiling "can be intrusive") | [metadata](https://docs.falkordb.com/browser/ui/metadata-view) |
| Schema view | Labels + relationship placements, property key types sampled from up to 10 elements per label, Unique/Mandatory badges, index types (range/fulltext/vector) | [schema](https://docs.falkordb.com/browser/ui/schema-view) |
| Data panel | Inspect/edit properties, add/remove labels (non-Read-Only) | [data](https://docs.falkordb.com/browser/ui/data-panel) |
| Chat panel | NL→Cypher; LLM from Settings: cloud keys (OpenAI, Anthropic, Gemini, Groq, Cohere, xAI, DeepSeek) or local Ollama (`http://localhost:11434`) / LM Studio (`http://localhost:1234/v1`); history 5–10 messages per tab+graph | [chat](https://docs.falkordb.com/browser/ui/chat-panel), [settings](https://docs.falkordb.com/browser/ui/settings) |
| Upload data | `LOAD CSV` (generated query you can edit; columns as `row.columnName`) or Cypher batch (`.cypher`/`.txt`, run sequentially) | [upload](https://docs.falkordb.com/browser/ui/upload-data) |
| Graphs Manager | Create / delete / **duplicate (with data)** / export `.dump` via `/api/graph/{graph}/export`. Duplicate = cheap "fork a tenant's memory" shot | [management](https://docs.falkordb.com/browser/ui/graph-management) |
| Swagger | `/docs`, OpenAPI at `/api/swagger`, Authorize + Try it out | [api docs](https://docs.falkordb.com/browser/ui/api-documentation) |
| Roles | Admin / Read-Write / Read-Only; read-only cannot create graphs; Admin sees DB Configurations + Users; personal access tokens | [roles](https://docs.falkordb.com/browser/ui/auth-access-control), [settings](https://docs.falkordb.com/browser/ui/settings) |
| UDF libraries | `/udf` page: load/flush/inspect JavaScript UDF libs | [udf](https://docs.falkordb.com/browser/ui/udf-libraries) |
| Navigation | Dark/Light/System theme, Offline indicator, Single/Sentinel/Cluster mode badges, guided tutorial replay | [nav](https://docs.falkordb.com/browser/ui/navigation) |
| Standalone Canvas | `npm install @falkordb/canvas`: `<falkordb-canvas>` web component, `setData`, `setLayout`, `zoomToFit`, event handlers, large-graph culling — can embed the same visualization in our own app | [canvas component](https://docs.falkordb.com/browser/canvas) |

Suggested demo beats **[Inference]**: (1) Schema view showing the memory ontology; (2) two tabs on two tenant graphs with Graph Info counts; (3) Table/Explain for a recall query; (4) Chat panel asking a NL question; (5) Read-Only user failing to create a graph; (6) Swagger `/docs` as proof of programmatic access.

---

## 6. Build vs reuse for Track 02 (inference, not docs)

Hackathon constraint (from the task brief): the main FalkorDB implementation must be new work done during the event; libraries are allowed.

| Criterion | Own layer on raw Cypher | Graphiti / Graphiti-MCP | Mem0 plugin | Cognee adapter |
|---|---|---|---|---|
| Counts as "new FalkorDB implementation" | Yes, fully | Weak: the graph logic is Zep's | Weak: plugin + Mem0 do the work | Weak |
| Needs LLM for every write | No (we choose) | Yes (extraction, embeddings) | Yes | Yes (`cognify`) |
| Episodic / semantic / procedural | We define labels; full control | Episodes ≈ episodic, entities/facts ≈ semantic, `Procedure` entity type | Flat facts + entity graph; procedural not documented | `TEMPORAL`, `CYPHER` search types; no explicit procedural |
| Persistent conversation history | Direct (message nodes) | Episodes (message type) | `history(memory_id)` per memory | Via `add` |
| Per-user/tenant isolation | Graph-per-tenant, our rule | `graph_name` (library) / `group_id` (MCP, mapping undocumented) | Automatic `{database}_{user_id}` | Not documented |
| Shared state + handoffs between agents | Our own `Task`/`Handoff` nodes, atomic via Cypher | Shared `group_id`, no handoff semantics documented | No | No |
| High-concurrency read/write demo | Directly measurable | Throttled by LLM (`SEMAPHORE_LIMIT`, default 10) | LLM-bound | LLM-bound |
| Demo reliability (offline, deterministic) | High | Needs API keys, rate limits (429 guidance in docs) | Needs keys | Needs keys, Python 3.11–3.13 only |
| Schema transparency in Browser | Ours | Documented schema conflicts internally (§1.2) | Mostly undocumented | Undocumented |
| Time cost | Highest, but small surface | Low | Low | Medium |

**Recommendation [Inference]:**
1. **Build the memory layer ourselves on raw Cypher** (graph-per-tenant, node types for episodic/semantic/procedural memory, conversation messages, tasks/handoffs, timestamps for decay or validity). This is the part that must be new work, it makes every Track 02 criterion directly demonstrable, and it avoids LLM latency/rate limits when showing concurrency.
2. **Reuse around it, not under it:** FalkorDB Browser for the demo and tenant inspection (§5); FalkorDB MCP Server in `FALKORDB_DEFAULT_READONLY=true` mode as a read-only agent-facing channel; optionally `FalkorDBSaver` / `FalkorDBChatMessageHistory` if a LangGraph/LangChain agent is part of the demo (verify the checkpoint/session graph layout first — undocumented).
3. **Use Graphiti or Mem0 only as a labelled baseline** (e.g. a comparison slide or an optional adapter), never as the core. If one must be picked: Mem0 has the clearest documented per-user graph isolation (`mem0_<user_id>`, drop to delete); Graphiti has the richest temporal and procedural modelling but its docs disagree with themselves on schema/graph naming and constructor, so budget time to verify against source.
4. Skip for this track: Snowflake, PyG, Jena, Spring Data, Kafka (unless we want an event-ingest scene), QueryWeaver, Code-Graph, AWS toolkit, n8n.

## Open items for the team
- Verify the actual Graphiti constructor/driver and the real node/edge labels by running the MCP image once and looking at the graph in Browser.
- Confirm in practice which graph `GRAPHITI_GROUP_ID` writes to (docs: undocumented).
- Confirm the `FalkorDBSaver` / `FalkorDBChatMessageHistory` graph schema by inspecting after a test run.
- The FalkorDB MCP server's complete tool list is not on these pages; read the [repo](https://github.com/FalkorDB/FalkorDB-MCPServer).
