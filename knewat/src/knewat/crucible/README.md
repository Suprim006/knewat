# Crucible: change only the backend, measure the rest

Methodology contract: `docs/BASELINE.md` (D-007). This package is the deterministic part: Layer 1 (correctness under
concurrency, C1-C8), Layer 4 (performance and scale) and the ablation. No LLM is involved.

## Run it

```bash
cd plexus
FALKORDB_PORT=6389 uv run crucible all --quick            # CI-sized (< 2 min), against a local FalkorDB
FALKORDB_PORT=6389 uv run crucible l1 --arms B1,P --tests C1,C3 --reps 3
uv run crucible l4 --arms B1 --workers 1,10,50            # baselines need no database
uv run crucible ablation                                  # Plexus with DEPENDS_ON / BASED_ON / DERIVED_FROM / READ deleted

# the published run: inside the compose network (no Docker Desktop port-forward in the latency)
export FALKORDB_PORT=6489 FALKORDB_BROWSER_PORT=3089 PLEXUS_API_PORT=18089 PLEXUS_MCP_PORT=18789
export CRUCIBLE_GIT_COMMIT=$(git rev-parse --short HEAD)
docker compose -p plexus-bench up -d falkordb
docker compose -p plexus-bench --profile bench run --rm -T crucible all
docker compose -p plexus-bench down -v
```

Output: `results/<timestamp>/results.json` + `report.md` (and `results/latest.json`, the file the View API serves via
`PLEXUS_RESULTS_PATH`). The schema is documented at the top of `results.py`. Exit code 1 means the **Plexus** arm
failed an L1 test; a baseline failing is a finding, not an error.

## Layout

| File | What |
|---|---|
| `api.py` | `CoordinationBackend` protocol (the tool surface), `Unsupported`, `BackendSpec` |
| `backends/files.py` | **B0** markdown memory + JSON task list under inter-process file locks, JSONL logs |
| `backends/sqlite.py` | **B1** SQLite WAL, `BEGIN IMMEDIATE`, FTS5, recursive CTEs |
| `backends/vector.py` | **B2** same embeddings as Plexus, numpy cosine; claims via B1's SQLite (hybrid) |
| `backends/plexus.py` | **P** / **P-mcp** the Plexus service layer (`P-mcp` = through `Runtime._run`: Step + ToolCall per call); `ablate()` |
| `l1.py` | C1-C8 |
| `victim.py` | C2's claimer process (killed with SIGKILL) |
| `l4.py` | claim / heartbeat / recall latency and throughput sweeps, one graph vs N tenant graphs |
| `ablation.py` | capability probes intact vs stripped; `P-abl` re-run of C4 and C8 |
| `results.py`, `report.py`, `cli.py` | assembly, markdown, command line |

Queries the Plexus arm needs beyond the product's own live in `plexus/queries/crucible/` (`list_tasks`, `strip_edges`).

## Rules the code follows

* The same tenant-name rule, task/fact semantics and normalisation in every arm (`api.py` docstring); the shared
  suite `tests/crucible/test_backends.py` pins them for all arms.
* Baselines are built competently (locks, transactions, FTS5, embeddings). If they tie Plexus, the report says so.
* Violations are exact counts summed over all runs; the harness is checked with deliberately broken arms
  (`tests/crucible/test_l1.py`, "negative controls").
* Synthetic data only.
