# F — FalkorDB GraphRAG SDK (reference)

Source: all 19 pages in `docs.falkordb.com/graphrag/*` + the [GitHub README](https://github.com/FalkorDB/GraphRAG-SDK). Base URL `https://docs.falkordb.com/graphrag/`; links below are `…/<page>.md`. "Not documented" = absent from these pages. Items marked **[inference]** are mine, not the docs'.

## 1. What it is, install, providers, minimal example

- Builds knowledge graphs from documents and answers questions over them; every pipeline step is a swappable strategy behind an ABC ([index](https://docs.falkordb.com/graphrag/index.md)). Python 3.10+, Apache-2.0, async-first; docs benchmark version is **1.3.0** ([README](https://github.com/FalkorDB/GraphRAG-SDK), [prereqs](https://docs.falkordb.com/graphrag/getting-started.md), [benchmark](https://docs.falkordb.com/graphrag/graphrag-accuracy-benchmark.md)). Pre-1.0 API: `pip install graphrag-sdk==0.8.2` ([README](https://github.com/FalkorDB/GraphRAG-SDK)).
- Install: `pip install graphrag-sdk[litellm]` (+`[pdf]`, `[markdown]`, `[openrouter]`, `[fastcoref]`, or `"graphrag-sdk[all]"`); FalkorDB: `docker run -p 6379:6379 falkordb/falkordb` ([index](https://docs.falkordb.com/graphrag/index.md), [getting-started](https://docs.falkordb.com/graphrag/getting-started.md), [strategies](https://docs.falkordb.com/graphrag/strategies.md)). Compatibility with FalkorDB 6.0 specifically: not documented (edge vector search says "FalkorDB >= 4.2", [storage](https://docs.falkordb.com/graphrag/storage.md)).
- Providers ([providers](https://docs.falkordb.com/graphrag/providers.md)): `LiteLLM`/`LiteLLMEmbedder` (recommended; 100+ providers, `provider/model` ids, e.g. `anthropic/claude-sonnet-4-20250514`), `OpenRouterLLM`/`OpenRouterEmbedder` (`OPENROUTER_API_KEY`), or subclass `LLMInterface` (only `invoke()` required) / `Embedder` (`model_name`, `embed_query()` required). Local models: custom subclass wrapping Ollama/vLLM. The embedder's `model_name` is used to validate that ingestion and retrieval use the same embedding model.
- Minimal end-to-end ([index](https://docs.falkordb.com/graphrag/index.md)):

```python
import asyncio
from graphrag_sdk import GraphRAG, ConnectionConfig, LiteLLM, LiteLLMEmbedder

async def main():
    async with GraphRAG(
        connection=ConnectionConfig(host="localhost", graph_name="my_graph"),
        llm=LiteLLM(model="openai/gpt-4o"),
        embedder=LiteLLMEmbedder(model="openai/text-embedding-3-small"),
    ) as rag:
        await rag.ingest("my_document.pdf")
        await rag.finalize()
        answer = await rag.completion("What is the main topic?")
        print(answer.answer)

asyncio.run(main())
```

- Raw text ingest: `await rag.ingest("acme_doc", text="…")`; sync wrappers `ingest_sync / retrieve_sync / completion_sync / finalize_sync` ([getting-started](https://docs.falkordb.com/graphrag/getting-started.md)). `embedding_dimension` (default 256) must match the embedder's output ([getting-started](https://docs.falkordb.com/graphrag/getting-started.md)).
- Multi-turn: `completion(question, history=[ChatMessage|dict])`, roles system/user/assistant; history goes to the LLM chat API, it is **not** written to the graph ([api-reference](https://docs.falkordb.com/graphrag/api-reference.md)).

## 2. Ingestion, extraction, entity resolution

**9-step pipeline** ([ingestion](https://docs.falkordb.com/graphrag/ingestion.md), [architecture](https://docs.falkordb.com/graphrag/architecture.md)): 1 Load (`LoaderStrategy`) → 2 Chunk → 3 Lexical graph (Document/Chunk nodes, `PART_OF`, `NEXT_CHUNK`; mandatory) → 4 Extract (+4b quality filter: drops empty/None ids and dangling edges) → 5 Prune against schema (skipped for empty schema; `"Unknown"` entities and `RELATES` always pass) → 6 Resolve → 7 Write (batched `UNWIND … MERGE`, 500/batch) → 8 `MENTIONED_IN` edges ∥ 9 embed+index chunks (steps 8–9 parallel). Then call `finalize()` **once** after all docs (not per doc).

**Extraction** — 2-step hybrid ([extraction](https://docs.falkordb.com/graphrag/extraction.md)):
- Step 1 NER: `GLiNERExtractor` (default, local, `urchade/gliner_medium-v2.1`, threshold 0.75, a band 25% below threshold kept as `"Unknown"`), `LLMExtractor(llm, threshold=0.75)`, or custom `EntityExtractor.extract_entities(text, entity_types, source_chunk_id)`. Optional `FastCorefResolver` (~1–2 s/chunk).
- Step 2: one LLM call per chunk verifies entities and extracts relationships (JSON with `source,target,type,description,keywords,weight,span_*`); on failure falls back to step-1 entities without relationships.
- Entity types priority: `schema.entities` > `entity_types=` > 11 defaults (Person, Organization, Technology, Product, Location, Date, Event, Concept, Law, Dataset, Method). Relation types: declared ontology relations (enforced, pruned) > `relation_types=` (preferred, not a filter) > `DEFAULT_RELATION_TYPES` (31 labels); `relation_types=[]` = open vocabulary ([extraction](https://docs.falkordb.com/graphrag/extraction.md)).
- Name gates: length 2–80, no pronouns/generic words; aggregation across chunks by `(name.lower(), type.lower())`; node id = `compute_entity_id` → `alice__person`.
- Doc timing: ~2–5 s per chunk (extraction is the slowest step) ([ingestion](https://docs.falkordb.com/graphrag/ingestion.md)).

**Resolution / dedup** ([ingestion](https://docs.falkordb.com/graphrag/ingestion.md), [storage](https://docs.falkordb.com/graphrag/storage.md), [strategies](https://docs.falkordb.com/graphrag/strategies.md)):
- At ingest (per document): `ExactMatchResolution` by `(normalized name, label)`; descriptions joined with `" | "`; no LLM. Opt-in `LLMVerifiedResolution` (embedding sim; ≥0.95 merge, 0.65–0.95 LLM YES/NO).
- `finalize()` (cross-document): P1 canonical-name match (case/accents/punctuation/article/legal-form normalised; acronym folding) → P2 optional fuzzy (cosine 0.95) → P3 `LLMVerifiedResolution` over whole graph (asks from cosine 0.6; NO stored as `DISTINCT_FROM`) → P4 `LLMJudgeDeduplicator` (candidate sets ≤8, judge twice with shuffled order; both agree → merge, one agrees → `SAME_AS` edge). Survivor ranking, alias/description/`source_chunk_ids` carry-over and edge remapping are in [storage](https://docs.falkordb.com/graphrag/storage.md). Measured: gpt-4.1 judge made 9 wrong merges vs 51 for gpt-4o-mini; `judge_vote=False` halves judge cost at ~3× wrong merges ([api-reference](https://docs.falkordb.com/graphrag/api-reference.md)). `finalize(resolve=False, judge=False)` calls no model.

**Structured ingestion** ([structured-ingestion](https://docs.falkordb.com/graphrag/structured-ingestion.md), [api-reference](https://docs.falkordb.com/graphrag/api-reference.md)): `.csv/.tsv/.psv/.tab` go through a deterministic, no-LLM path driven by `Ontology(tables=[TableMapping(source, label, key, name, properties={…Column(name,type)}, links=[Link(type,to,by)])])`. Each row = one `Chunk` (`kind:"record"`, **not embedded**, not `NEXT_CHUNK`-chained); typed properties are stored signed as `<file>__<prop>` (e.g. `employees__age`); links become `RELATES` edges (`rel_type`), targets created as `is_stub` placeholders until the owning table arrives. Re-ingest = snapshot re-sync (deleted rows removed; content hash incl. mapping). Rows and prose join through the shared name-derived id. ~1,300–3,000 rows/s measured. No mapping declared → LLM proposes one (stored `derived=True`).

## 3. Retrieval, grounding, provenance, abstention

**`MultiPathRetrieval` (default)** ([retrieval](https://docs.falkordb.com/graphrag/retrieval.md)): keyword extraction (stopword filter + 1 LLM call) → embed question → (3a) `RELATES` edge vector search (fact strings + entry entities) ∥ (3b) optional text-to-Cypher → entity discovery (Cypher `CONTAINS` + fulltext on `__Entity__`) → 1-hop/2-hop relationship expansion → chunk retrieval via 4 paths (fulltext, vector, `MENTIONED_IN`, entity→neighbour→chunk) → map chunks to `Document.path` → cosine rerank on **stored** chunk embeddings (top 15) + fact filter (min_score 0.25, keep ≥3, max 12) → assemble sections `hint`, `cypher_results`, `entities`, `relationships`, `facts`, `passages` ([reliability-and-grounding](https://docs.falkordb.com/graphrag/reliability-and-grounding.md)).
- Text-to-Cypher: `enable_cypher=False` by default, +~1.5 s and one LLM call; results bypass reranking; a hand-built strategy must be given `ontology=await rag.get_ontology()` ([retrieval](https://docs.falkordb.com/graphrag/retrieval.md), [reliability](https://docs.falkordb.com/graphrag/reliability-and-grounding.md)). Other strategy: `LocalRetrieval` (chunk vector + 1-hop; `top_k=5`) ([strategies](https://docs.falkordb.com/graphrag/strategies.md)).
- Doc's own isolated-path accuracy on a 100-question set: vector 77.4%, fulltext 74.8%, RELATES 70.0%, MENTIONED_IN 69.1%, text-to-Cypher 53.0%; fused 83.8% (84.8% with all enhancements); P50 latency 4.2 s (5.7 s with Cypher) ([retrieval](https://docs.falkordb.com/graphrag/retrieval.md)).

**Grounding / provenance / abstention APIs** ([reliability-and-grounding](https://docs.falkordb.com/graphrag/reliability-and-grounding.md), [reducing-llm-hallucinations](https://docs.falkordb.com/graphrag/reducing-llm-hallucinations.md)):
- `completion()` answers from a `<context>` block under a "use ONLY the context" system prompt (rule 6: say if insufficient). A custom `prompt_template=` (needs `{context}` and `{question}`) disables the `</context>` neutralisation and the delimited prompt.
- Evidence trail: `completion(q, return_context=True)` → `RagResult.retriever_result.items` (`content`, `metadata["section"]`, `score`); passages are prefixed `[Source: <path>]`; `result.metadata` has `num_context_items`, `strategy`, `retrieval_query`. Chain: `Document -PART_OF-> Chunk <-MENTIONED_IN- __Entity__`; `RELATES.source_chunk_ids`.
- `retrieve()` = retrieval without generation (still makes the keyword LLM call). `chunk_id` in item metadata is only set by `LocalRetrieval`.
- **Abstention is prompt-level only; no enforcement, no confidence score on the answer.** `MultiPathRetrieval` items have `score=None` unless a `CosineReranker(embedder, top_k)` is attached (section-level scores run lower than chunk-level). No similarity floor on chunk retrieval; fact filter keeps ≥3 regardless. Documented gate pattern: `retrieve()` → count non-`hint` items / score threshold → fixed refusal string, else `completion()`; costs an extra retrieval and 3 LLM calls vs 2 on answered questions.
- Metadata filtering: no `filter=` argument; use Cypher on loader-supplied `Document` properties, or one graph per scope (`graph_name`).

## 4. Graph schema created in FalkorDB (exact)

From [graph-schema](https://docs.falkordb.com/graphrag/graph-schema.md), [storage](https://docs.falkordb.com/graphrag/storage.md), [architecture](https://docs.falkordb.com/graphrag/architecture.md), [incremental-updates](https://docs.falkordb.com/graphrag/incremental-updates.md), [reliability](https://docs.falkordb.com/graphrag/reliability-and-grounding.md), [structured-ingestion](https://docs.falkordb.com/graphrag/structured-ingestion.md), [strategies](https://docs.falkordb.com/graphrag/strategies.md), [ontology-evolution](https://docs.falkordb.com/graphrag/ontology-evolution.md):

| Node | Properties |
|---|---|
| `Document` | `id` (UUID per graph-schema page; `document_id`/normalised path per reliability page), `path`, `content_hash`, loader metadata (`loader,size_bytes,suffix` / `page_count,pdf_backend`); transient `pending_delete`, `ready_to_commit`; `__pending__` doc during `update()` |
| `Chunk` | `id`, `text`, `index`, `embedding` (vecf32), `start_char,end_char,chunk_size,chunk_overlap` (FixedSize); `breadcrumbs` (StructuralChunking); `kind:"record"`, `record_key` + cells (tables); `extracted_ops` marker (evolution) |
| `<Label>:__Entity__` (e.g. `Person`) | `id` (`name__type`), `name`, `description`, `source_chunk_ids`, `spans` (JSON string), `embedding` (name, from `finalize()`); merge adds `aliases`, `descriptions`, `merged_labels`; tables add `entity_key`, `is_stub`, `<file>__<prop>` |

| Edge | Direction / properties |
|---|---|
| `PART_OF` | Document→Chunk; `index` |
| `NEXT_CHUNK` | Chunk→Chunk; none |
| `MENTIONED_IN` | `__Entity__`→Chunk; none; unique per (entity, chunk) |
| `RELATES` | `__Entity__`→`__Entity__`, the **only** knowledge edge type: `rel_type`, `fact`, `description`, `keywords`, `weight`, `src_name`, `tgt_name`, `source_chunk_ids`, `spans`, `embedding` (of `fact`) |
| `SAME_AS` / `DISTINCT_FROM` | written by dedup (`source='llm_judge'`, `agreement`) / resolver NO-verdicts |

Weight: 1.0 explicit, 0.5 implied ([extraction](https://docs.falkordb.com/graphrag/extraction.md)); graph-schema adds 0.2 weak inference. Single `RELATES` type = one edge vector index instead of hundreds. Query by type: `MATCH (a:Person)-[r:RELATES {rel_type: "WORKS_AT"}]->(b:Organization)`.

**Indexes (5, idempotent, created by `finalize()`/`ensure_indices()`)**: vector on `Chunk.embedding`, `__Entity__.embedding`, `RELATES.embedding`; fulltext on `Chunk(text)`, `__Entity__(name, description)`. Exact syntax in [graph-schema](https://docs.falkordb.com/graphrag/graph-schema.md):

```
CREATE VECTOR INDEX FOR (n:Chunk) ON (n.embedding)
OPTIONS {dimension:256, similarityFunction:'cosine'}
CALL db.idx.fulltext.createNodeIndex('Chunk', 'text')
CALL db.idx.fulltext.createNodeIndex('__Entity__', 'name', 'description')
```

Edge index (from storage page, label backtick-quoted there): ``CREATE VECTOR INDEX FOR ()-[e:`RELATES`]->() ON (e.embedding) OPTIONS {dimension:256, similarityFunction:'cosine'}``; search via `db.idx.vector.queryNodes` / `queryRelationships` ([storage](https://docs.falkordb.com/graphrag/storage.md)). A separate "ontology graph" holds `:Property` declarations; its exact layout is not documented ([ontology-evolution](https://docs.falkordb.com/graphrag/ontology-evolution.md)). `delete_all()` uses `GRAPH.DELETE`.

## 5. Ontology discovery/evolution, incremental updates

- **Discovery** ([ontology-discovery](https://docs.falkordb.com/graphrag/ontology-discovery.md)): `Ontology.from_sources(sources, llm, method="llm"|"grounded", boundaries=, existing=, sample_chunks_per_doc=3)`; `"llm"` costs ≈`D×(S+1)+1` calls; `"grounded"` uses `DBpediaCatalog` (live DBpedia SPARQL + Schema.org, no offline fallback, zero LLM calls). `rag.suggest_schema_extensions(new_docs)` returns an additions-only `SchemaExtensionProposal`; nothing is auto-applied.
- **Evolution** ([ontology-evolution](https://docs.falkordb.com/graphrag/ontology-evolution.md)): 15 methods. Declarations (`add_entity`, `add_relation_pattern`, `set_*_description`) are cheap; renames/drops are Cypher migrations; `add_attribute` is atomic — LLM-backfills every chunk mentioning the owner type, then commits the schema (use `dry_run=True` to preview cost; idempotent retry via `extracted_ops`); `backfill_entity/_relation_pattern` are opt-in. No `retype_attribute`; relation-attribute mutation raises `NotImplementedError`. **Not safe to run concurrently with `ingest()`** or each other.
- **Incremental** ([incremental-updates](https://docs.falkordb.com/graphrag/incremental-updates.md)): `update(source|text, document_id, if_missing="error"|"ingest", force=False)` — SHA-256 `content_hash` no-op short-circuit, new chunks written to a pending Document then atomically cut over, orphan entities/`RELATES` (keyed on `source_chunk_ids`) pruned, scoped to the touched doc; `delete_document(id, if_missing=)`; `apply_changes(added, modified, deleted, max_concurrency=3, update_concurrency=1)` runs deletes→updates→adds, never raises per file (`BatchEntry`), no auto-`finalize()`. `finalize()` cost is O(graph size) ([README](https://github.com/FalkorDB/GraphRAG-SDK)).

## 6. Strategy ABCs and configuration (compact)

ABCs ([strategies](https://docs.falkordb.com/graphrag/strategies.md), [architecture](https://docs.falkordb.com/graphrag/architecture.md)):

| ABC | Method | Built-ins |
|---|---|---|
| `LoaderStrategy` | `load(source, ctx)` | `TextLoader`, `PdfLoader`, `MarkdownLoader` |
| `ChunkingStrategy` | `chunk(text, ctx)` | `FixedSizeChunking(1000/100)`, `SentenceTokenCapChunking(384, overlap 2)`, `ContextualChunking` (1 LLM call/chunk), `CallableChunking`, `StructuralChunking` |
| `ExtractionStrategy` | `extract(chunks, schema, ctx)` | `GraphExtraction` |
| `ResolutionStrategy` | `resolve(graph_data, ctx)` | `ExactMatchResolution`, `LLMVerifiedResolution` |
| `RetrievalStrategy` | `_execute(query, ctx)` | `LocalRetrieval`, `MultiPathRetrieval` |
| `RerankingStrategy` | `rerank(query, result, ctx)` | `CosineReranker(top_k=15)` |

Also `EntityExtractor`, `CorefResolver`, `RecordLoaderStrategy`, `Catalog`. Inconsistency: ingestion/strategies pages state `FixedSizeChunking` as default, while [api-reference](https://docs.falkordb.com/graphrag/api-reference.md) says `SentenceTokenCapChunking()` is the `ingest()` default and [benchmark](https://docs.falkordb.com/graphrag/benchmark.md) says its max_tokens went 512→384.

Config ([configuration](https://docs.falkordb.com/graphrag/configuration.md), [api-reference](https://docs.falkordb.com/graphrag/api-reference.md), [retrieval](https://docs.falkordb.com/graphrag/retrieval.md)):

| Setting | Default |
|---|---|
| `ConnectionConfig` | host `localhost`, port 6379, graph_name `knowledge_graph`, max_connections 16, retry_count 3, retry_delay 1.0, pool_timeout 30, query_timeout_ms 10000; `from_url("redis://…")` |
| `GraphRAG(…)` | `ontology=None` (`schema=` deprecated alias), `retrieval_strategy=None`, `embedding_dimension=256`, `enable_cypher=False` |
| `LiteLLM` | temperature 0.0, max_tokens None; `LLMInterface.max_concurrency` 12 |
| `LiteLLMEmbedder` | `batch_size` 2048 (Azure: 500); binary-split retry on batch errors |
| `ingest()` | `max_concurrency=3` (list input) |
| `MultiPathRetrieval` | chunk_top_k 15, max_entities 30, max_relationships 20, rel_top_k 15, keyword_limit 10, enable_cypher False |
| `LLMVerifiedResolution` | hard 0.95, soft 0.65, max_llm_pairs 500, ann_top_k 50 |
| `finalize()` | resolve=True, judge=True, judge_vote=True, judge_llm=None (uses main LLM) |
| `deduplicate_entities()` | fuzzy False, similarity_threshold 0.95, batch_size 500, judge False |
| `Context` | tenant_id `"default"`, latency_budget_ms 60000 |

Retry: transient query failures retried with backoff plus a circuit breaker ([storage](https://docs.falkordb.com/graphrag/storage.md)); docs differ on linear vs exponential backoff ([configuration](https://docs.falkordb.com/graphrag/configuration.md)).

## 7. Benchmark claims and caveats

- Claim: GraphRAG SDK 1.3.0 scores **71.48** overall vs **55.39** for vector RAG with rerank on GraphRAG-Bench (Xiang et al., ICLR 2026): Novel 66.09 vs 48.35, Medical 76.87 vs 62.43; +16.09 points, ~29% relative; same `gpt-4o-mini` backbone and judge ([accuracy page](https://docs.falkordb.com/graphrag/graphrag-accuracy-benchmark.md)). Ranked #1 of 16 listed systems on both subsets ([benchmark](https://docs.falkordb.com/graphrag/benchmark.md)). Per-category Novel ACC: fact 65.49, reasoning 59.26, summarize 75.42, creative 64.21.
- Methodology: ACC = unweighted mean of four categories; Overall = (Novel+Medical)/2, "our own cross-dataset summary", not a leaderboard figure; judge = benchmark's unmodified `generation_eval.py` with gpt-4o-mini, temp 0, seed 42.
- Caveats stated by the docs ([accuracy page](https://docs.falkordb.com/graphrag/graphrag-accuracy-benchmark.md), [benchmark](https://docs.falkordb.com/graphrag/benchmark.md)): competitors not re-run (August 2026 leaderboard); Novel has 2,009 predictions for 2,010 questions (duplicate id); evaluator skipped unscorable samples (2,053/2,062 Medical, 1,995/2,009 Novel); LLM-judge variance; two domains only; "does not measure hallucination rate on your data".
- Caveats I add **[inference]**: vendor-run; two declared deviations from defaults (`enable_cypher=True`, 1024-dim embeddings — text-to-Cypher touched 22% Medical / 29% Novel answers) while the SDK's retrieval defaults are otherwise kept; **hand-authored per-corpus ontologies**; one graph per document (the setup removes cross-document noise); generation temp 0.7; chunking default stated as 512 on one page and 384 on another; the doc's own text-to-Cypher-off ablation is a separate 100-question set, not the leaderboard setup. Benchmark tasks are document QA, not memory recall; the docs themselves say nothing about conversational memory.

## 8. Is it useful for Track 02 (agent memory & coordination)? **[inference — not from docs]**

The docs never mention agent memory, sessions, temporal validity or multi-agent coordination. README roadmap lists "Agentic GraphRAG" (2026-Q3) and "temporal graph" (2026-Q4) as future ([README](https://github.com/FalkorDB/GraphRAG-SDK)) — i.e. temporal memory is **not** shipped.

**Reusable ideas/pieces**
- *Semantic-memory extraction from turns*: treat each turn/session as a "document" (`ingest(text=…, document_id="session-42")`), extract with a small custom `Ontology` (Person, Preference, Task, Tool…); `relation_types` and `Ontology.relations` constrain edges ([extraction](https://docs.falkordb.com/graphrag/extraction.md)). GLiNER NER is local/free; the only per-chunk LLM cost is step 2.
- *Provenance model* maps well to episodic→semantic memory: `Document(episode) → Chunk(turn) ← MENTIONED_IN ← Entity`, plus `RELATES.source_chunk_ids` ([graph-schema](https://docs.falkordb.com/graphrag/graph-schema.md)). Gives "why do I believe this?" for free.
- *Incremental updates*: `update()`/`delete_document()` with scoped orphan cleanup = a principled "forget/replace this episode" operation; hash no-op avoids re-paying LLM cost ([incremental-updates](https://docs.falkordb.com/graphrag/incremental-updates.md)).
- *Abstention gate* (`retrieve()` → score threshold → refuse) is directly reusable for "I don't remember" ([reducing-llm-hallucinations](https://docs.falkordb.com/graphrag/reducing-llm-hallucinations.md)).
- *Isolation*: `graph_name` per agent/tenant ([reliability](https://docs.falkordb.com/graphrag/reliability-and-grounding.md)); `DISTINCT_FROM`/`SAME_AS` give auditable identity decisions; ontology evolution lets the memory schema grow.
- *Structured ingestion* could load agent task tables / tool registries deterministically alongside conversational facts, joined by name ([structured-ingestion](https://docs.falkordb.com/graphrag/structured-ingestion.md)).
- Retrieval ideas worth copying even without the SDK: embedding facts on a single edge type for one vector index; fact-vs-passage separate thresholds ([retrieval](https://docs.falkordb.com/graphrag/retrieval.md)).

**Where it doesn't fit**
- Document-RAG shape: chunks of static text, prose QA; no notion of fact supersession (a changed preference becomes a second `RELATES` edge or needs a full `update()` of the source doc), no timestamps/validity intervals on edges (not documented), no importance/decay.
- Entity embeddings are of names only; dedup quality depends on `finalize()`, which is global, O(graph size), and by default makes LLM-judge calls — docs say don't call it per document ([ingestion](https://docs.falkordb.com/graphrag/ingestion.md)). A per-turn write path would either skip `finalize()` (leaving duplicates and no entity/edge vector search) or pay it repeatedly.
- No coordination primitives (locks, shared blackboard, agent identity, concurrent-writer semantics) documented; evolution calls are unsafe alongside ingestion; `update_concurrency` should stay 1 ([incremental-updates](https://docs.falkordb.com/graphrag/incremental-updates.md)).
- `completion(history=)` carries conversation to the LLM only; it is not persisted as memory.
- Abstention/confidence are DIY; `MultiPathRetrieval` scores are not surfaced.
- Python-only SDK, heavy dependencies (GLiNER model download, optional fastcoref); the project's own hackathon constraints on using third-party SDKs are not covered here.

**Cost/latency**
- Ingestion: ~2–5 s and ≥1 LLM call per chunk; 1 embedding batch call per ingest; benchmark indexing 510 chunks ≈1.5 h, ~2,500 chunks ≈4 h on 24 cores ([benchmark](https://docs.falkordb.com/graphrag/benchmark.md)). Short turns = one chunk each, so ~seconds per turn **[inference]**.
- Query: every `retrieve()`/`completion()` makes an LLM keyword call (+1 for Cypher, +1 generation); doc P50 4.2 s fused, 5.7 s with Cypher ([retrieval](https://docs.falkordb.com/graphrag/retrieval.md)). Abstention gate adds a second retrieval.
- Finalize: embeddings for names/facts + dedup scan + resolver/judge LLM calls (gpt-4.1-class recommended) ([api-reference](https://docs.falkordb.com/graphrag/api-reference.md)).
- `add_attribute` = one LLM call per relevant chunk ([ontology-evolution](https://docs.falkordb.com/graphrag/ontology-evolution.md)).

**Bottom line [inference]**: borrow the schema (lexical + knowledge layers, `MENTIONED_IN`, single `RELATES` edge with `rel_type`/`fact`/`source_chunk_ids`, 3 vector + 2 fulltext indexes), the extraction approach, and the abstention gate; do not expect it to supply temporal memory, supersession, or agent coordination — those would be our own contribution on top of FalkorDB.
