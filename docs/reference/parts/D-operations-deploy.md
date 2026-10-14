# D — Operations & Deployment (FalkorDB docs digest)

Source: docs.falkordb.com `operations/*`, `operations/durability/*`, `operations/falkordblite/*`, `operations/migration/*`, `cloud/*` (non-API), `enterprise/*` (non-API). 95 pages fetched and read; Enterprise pages skimmed.
Tags: **[CONFLICT]** = two doc pages disagree; **[INFERENCE]** = my reading, not stated in docs; "not documented" = absent from these pages.
Product scope: sections 1-6 = FalkorDB core (self-hosted); section 7 = FalkorDB Cloud; section 8 = FalkorDB Enterprise (self-managed K8s).

---
## 1. Docker / Docker Compose

Source page: [operations/docker](https://docs.falkordb.com/operations/docker.md); overview in [operations/index](https://docs.falkordb.com/operations/index.md).

### Images and ports ([docker](https://docs.falkordb.com/operations/docker.md))
| Image | Contains | Ports | Use |
|---|---|---|---|
| `falkordb/falkordb` | server + Browser UI | 6379 (server), 3000 (Browser) | dev / quick start |
| `falkordb/falkordb-server` | server only | 6379 | production, lighter ([index](https://docs.falkordb.com/operations/index.md)) |
| `falkordb/falkordb-browser` | Browser UI only | 3000 | needs env `FALKORDB_URL` pointing to a server |

### Run commands (copied from [docker](https://docs.falkordb.com/operations/docker.md))
```bash
docker run -p 6379:6379 -p 3000:3000 -it --rm falkordb/falkordb:latest
docker run -p 6379:6379 -it --rm falkordb/falkordb-server:latest
docker run -p 6379:6379 -p 3000:3000 -it \
  -e REDIS_ARGS="--requirepass yourpassword" \
  --rm falkordb/falkordb:latest
docker run -p 6379:6379 -p 3000:3000 -it \
  -e REDIS_ARGS="--requirepass yourpassword" \
  -e FALKORDB_ARGS="THREAD_COUNT 4 TIMEOUT 5000" \
  --rm falkordb/falkordb:latest
```

### Environment variables ([docker](https://docs.falkordb.com/operations/docker.md))
- `REDIS_ARGS` — passed to `redis-server`. Listed examples: `--requirepass <pw>`, `--appendonly yes`, `--appendfsync everysec`, `--maxmemory <bytes>`, `--maxmemory-policy <policy>` (e.g. `allkeys-lru`). Also used for `--aclfile` ([acl-persistence](https://docs.falkordb.com/operations/durability/acl-persistence.md)) and `--dir/--dbfilename` ([redisgraph migration](https://docs.falkordb.com/operations/migration/redisgraph-to-falkordb.md)).
- `FALKORDB_ARGS` — module config, e.g. `THREAD_COUNT 4 CACHE_SIZE 25 TIMEOUT_MAX 10000`; full parameter list is on `/getting-started/configuration` (not in this part). Compose examples also use `TIMEOUT_DEFAULT 30000`, `QUERY_MEM_CAPACITY 104857600`.
- `BROWSER=0` — used in the cluster guide to disable the Browser ([cluster](https://docs.falkordb.com/operations/cluster.md)); not explained elsewhere.
- Browser container: `FALKORDB_URL=redis://falkordb-server:6379`, `FALKORDB_PASSWORD=...` ([docker](https://docs.falkordb.com/operations/docker.md)).
- **[CONFLICT]** The cluster guide puts Redis flags inside `FALKORDB_ARGS` (`--port … --cluster-enabled yes --cluster-announce-ip …`) ([cluster](https://docs.falkordb.com/operations/cluster.md)), while the Docker page says Redis flags go in `REDIS_ARGS` and `FALKORDB_ARGS` takes bare module parameters (`THREAD_COUNT 4`). Unresolved in docs; prefer the form each page shows for its own scenario.

### Authentication
`--requirepass` via `REDIS_ARGS` ([docker](https://docs.falkordb.com/operations/docker.md)). Healthcheck with auth: `["CMD","redis-cli","-a","yourpassword","ping"]`. ACL users: see §2.3.

### Compose — production example from the docs ([docker](https://docs.falkordb.com/operations/docker.md))
```yaml
version: '3.8'
services:
  falkordb:
    image: falkordb/falkordb-server:latest
    container_name: falkordb-production
    ports:
      - "6379:6379"
    environment:
      # Redis Configuration
      - REDIS_ARGS=--requirepass ${FALKORDB_PASSWORD:-changeme} --appendonly yes --appendfsync everysec --maxmemory 2gb --maxmemory-policy allkeys-lru
      # FalkorDB Configuration
      - FALKORDB_ARGS=THREAD_COUNT 8 CACHE_SIZE 50 TIMEOUT_MAX 60000 TIMEOUT_DEFAULT 30000 QUERY_MEM_CAPACITY 104857600
    volumes:
      - falkordb_data:/data
      - ./falkordb-config:/etc/falkordb
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "$${FALKORDB_PASSWORD:-changeme}", "ping"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    networks:
      - falkordb-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
volumes:
  falkordb_data:
    driver: local
networks:
  falkordb-network:
    driver: bridge
```
Other Compose facts from the same page: `docker-compose up -d`, `docker-compose logs -f`, `docker-compose down` (keeps volumes), `docker-compose down -v` (**deletes data**), `docker-compose exec falkordb redis-cli`. Resource limits snippet: `deploy.resources.limits {cpus: '4', memory: 8G}`, `reservations {cpus: '2', memory: 4G}`. `.env` file pattern: `FALKORDB_PASSWORD=...` referenced as `${FALKORDB_PASSWORD}`. Use `expose:` (internal only) instead of `ports:` to keep 6379 off the host. A ready-made `docker-compose.yml` lives at github.com/FalkorDB/FalkorDB/blob/master/build/docker/docker-compose.yml (linked from the same page).
Pin versions: page example is `image: falkordb/falkordb-server:4.0.0` (an example tag; actual current tags not documented in these pages — check Docker Hub).

### Data-dir path **[CONFLICT]**
- The Docker page's Compose examples mount `falkordb_data:/data`; its FAQ says to mount `/var/lib/falkordb/data` ([docker](https://docs.falkordb.com/operations/docker.md)); the index FAQ says `/var/lib/falkordb/data` ([index](https://docs.falkordb.com/operations/index.md)); [persistence](https://docs.falkordb.com/operations/durability/persistence.md) and [acl-persistence](https://docs.falkordb.com/operations/durability/acl-persistence.md) state "default data directory" = `/var/lib/falkordb/data`; [replication](https://docs.falkordb.com/operations/replication.md) and the RedisGraph migration (`--dir /data`) use `/data`.
- Docs never say whether `/data` is a symlink/alias. **Verify with `docker exec <c> redis-cli CONFIG GET dir` before trusting a volume mount** [INFERENCE].

### Building images from source ([building-docker](https://docs.falkordb.com/operations/building-docker.md))
Dockerfiles are generated by the `readies` `dockerwrapper` script; needs python >3.6, `jinja2`, docker. Page lists package-install command sequences for CentOS 7, Ubuntu 18.04, Debian 10, Alpine 3 (build deps: build-essential/peg/cmake 3.21.1/valgrind etc.). Not needed for a hackathon.

---
## 2. Persistence & backup

### 2.1 RDB / AOF ([durability](https://docs.falkordb.com/operations/durability/index.md))
- Two mechanisms: RDB (point-in-time snapshots to `dump.rdb`) and AOF (write log). Can be used alone or together; **on restart the AOF is used if present**.
- RDB config: `save 60 1000`, `save 300 100`, `save 900 1`, `dir /var/lib/falkordb/data`, `dbfilename dump.rdb`. Fork can pause for ms–~1 s on very large datasets.
- AOF config: `appendonly yes`, `appendfilename "appendonly.aof"`, `appendfsync always|everysec|no` (`everysec` recommended/default, max ~1 s loss, ~1-2 % overhead; `always` = latest command only at risk but slow; `no` = OS decides, ~30 s on Linux). Rewrite: `auto-aof-rewrite-percentage 100`, `auto-aof-rewrite-min-size 64mb`, manual `redis-cli BGREWRITEAOF`.
- Doc's recommended preset: `save 900 1 / save 300 10 / save 60 1000 / appendonly yes / appendfsync everysec`. Dev preset: `save ""` + `appendonly no`.
- Inspect/force: `redis-cli INFO persistence` (look at `rdb_last_save_time`, `aof_enabled`, `aof_last_rewrite_status`), `SAVE` (blocking), `BGSAVE`, `BGREWRITEAOF`.
- In Docker these are passed through `REDIS_ARGS` (e.g. `--appendonly yes`), see [acl-persistence](https://docs.falkordb.com/operations/durability/acl-persistence.md).

### 2.2 Docker volume persistence ([persistence](https://docs.falkordb.com/operations/durability/persistence.md))
```bash
docker volume create falkordb_data
docker run -d --name falkordb -v falkordb_data:/var/lib/falkordb/data -p 6379:6379 falkordb/falkordb
# verify
redis-cli GRAPH.QUERY mygraph "CREATE (:Database {name:'falkordb'})"
docker stop falkordb
docker start falkordb
redis-cli GRAPH.QUERY mygraph "MATCH (n) RETURN n"
```
Note: this example does **not** set `--appendonly yes`; survival of a plain stop/start relies on RDB (shutdown save) — the page doesn't discuss this [INFERENCE]. Named volumes preferred over bind mounts.

### 2.3 ACL persistence ([acl-persistence](https://docs.falkordb.com/operations/durability/acl-persistence.md))
ACL users made with `ACL SETUSER` are in-memory only. Use an ACL file:
```bash
mkdir -p ~/falkordb/data
touch ~/falkordb/data/users.acl        # MUST exist before start, else Redis refuses to start
docker run -d --name falkordb \
  -p 6379:6379 \
  -v ~/falkordb/data:/var/lib/falkordb/data \
  -e REDIS_ARGS="--appendonly yes --aclfile /var/lib/falkordb/data/users.acl" \
  falkordb/falkordb:latest
redis-cli ACL SETUSER alice on '>secret123' '~*' '&*' '+@all'
redis-cli ACL SETUSER bob   on '>bobpass'   '~bob:*' '+@read' '+GRAPH.QUERY' '+GRAPH.RO_QUERY'
redis-cli ACL SAVE        # required, otherwise lost on restart
redis-cli CONFIG GET aclfile
redis-cli --user alice --pass secret123 --no-auth-warning PING
```
Compose form: `environment: REDIS_ARGS: "--appendonly yes --aclfile /var/lib/falkordb/data/users.acl"`, volume `./data:/var/lib/falkordb/data`, `touch ./data/users.acl` before first `docker compose up`.
Notes from page: run `ACL SETUSER default off` once an admin user with `+@all` exists; `chmod 600` the file (contains hashes); Snap-installed Docker only bind-mounts under the home dir; with `aclfile` set you cannot also have `user` lines in redis.conf; `ACL SAVE` without `aclfile` errors "This Redis instance is not configured to use an ACL file".

### 2.4 DUMP / RESTORE per graph ([durability](https://docs.falkordb.com/operations/durability/index.md))
A graph is a Redis key, so `DUMP`/`RESTORE` work per graph (selective backup, clone to test, migrate between instances). The page shows:
```bash
redis-cli DUMP mygraph > mygraph.dump
redis-cli --pipe < mygraph.dump        # as written in docs
redis-cli RESTORE mygraph 0 "<serialized-value>"
```
RESTORE options listed: `REPLACE`, `ABSTTL`, `IDLETIME`. DUMP does not include TTL. **Caveat [INFERENCE]**: `redis-cli DUMP` prints an escaped string on a TTY and `--pipe` expects Redis protocol, so those two lines likely do not round-trip as written; test before relying on them, or use RDB file copy / client-library DUMP. Also GRAPH.COPY exists as a command (seen in Cloud role lists, [user-management](https://docs.falkordb.com/cloud/operations/user-management.md)) but is documented elsewhere.

### 2.5 Backup best practices (docs) ([durability](https://docs.falkordb.com/operations/durability/index.md))
Scheduled RDB via cron, off-site copies, test restores, watch disk space for both RDB and AOF, automate rotation. Railway/K8s equivalents: §3.

---
## 3. Replication, cluster, Kubernetes, platforms

### 3.1 Replication ([replication](https://docs.falkordb.com/operations/replication.md))
Single primary, async replicas; replicas read-only (use `GRAPH.RO_QUERY`).
```bash
docker network create falkordb-network
docker run -d --name falkordb-master -v falkordb_data:/data -p 6379:6379 --network falkordb-network falkordb/falkordb
docker run -d --name falkordb-replica1 -p 6380:6379 --network falkordb-network falkordb/falkordb
docker exec -it falkordb-replica1 /bin/bash
redis-cli replicaof falkordb-master 6379
```
Verify: write on master with `GRAPH.QUERY`, read on replica with `GRAPH.RO_QUERY`; lag via `INFO replication`. No automatic failover without Sentinel or cluster. No auth (`masterauth`/`requirepass`) example given — not documented. `REPLICAOF` issued at runtime is not persisted unless config is rewritten [INFERENCE].

### 3.2 Cluster ([cluster](https://docs.falkordb.com/operations/cluster.md))
Redis Cluster, 16,384 slots; **each graph = one key = one shard** (clustering distributes different graphs, never splits one graph). Cluster-aware client needed (`redis-cli -c`; `MOVED` redirects).
```bash
docker network create falkordb-cluster-network
for i in {1..6}; do
  docker run -d \
    --name node$i \
    --hostname node$i \
    --network falkordb-cluster-network \
    -p $((6379 + i - 1)):$((6379 + i - 1)) \
    -e BROWSER=0 \
    -e "FALKORDB_ARGS=--port $((6379 + i - 1)) --cluster-enabled yes --cluster-announce-ip node$i --cluster-announce-port $((6379 + i - 1))" \
    falkordb/falkordb
done
for i in {1..6};do sudo echo "127.0.0.1 node$i" | sudo tee -a /etc/hosts; done
docker exec -it node1 redis-cli --cluster create node1:6379 node2:6380 node3:6381 node4:6382 node5:6383 node6:6384 --cluster-replicas 1 --cluster-yes
docker exec -it node1 redis-cli --cluster check node1:6379
redis-cli -c GRAPH.QUERY network "UNWIND range(1, 100) AS id CREATE (n:Person {id: id, name: 'Person ' + toString(id), age: 20 + id % 50})"
# add a node
docker exec -it node1 redis-cli --cluster add-node node7:6385 node1:6379
```
(node7 `docker run` is the same pattern with port 6385.) On Windows the `/etc/hosts` step is the Windows hosts file instead [INFERENCE]. Failover: replica auto-promotes via cluster consensus (FAQ). Minimum 3 masters recommended.

### 3.3 Kubernetes + Helm (Bitnami) ([k8s-support](https://docs.falkordb.com/operations/k8s-support.md))
Sentinel-based HA (Option A), `values.yaml`:
```yaml
global:
  security:
    allowInsecureImages: true
image:
  registry: docker.io
  repository: falkordb/falkordb
  tag: "latest"
master:
  extraFlags:
  - "--loadmodule /var/lib/falkordb/bin/falkordb.so"
replica:
  extraFlags:
  - "--loadmodule /var/lib/falkordb/bin/falkordb.so"
```
```bash
helm install -f values.yaml my-falkordb oci://registry-1.docker.io/bitnamicharts/redis
export REDIS_PASSWORD=$(kubectl get secret --namespace default my-falkordb-redis -o jsonpath="{.data.redis-password}" | base64 -d)
kubectl port-forward --namespace default svc/my-falkordb-redis-master 6379:6379
REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli -h 127.0.0.1 -p 6379
```
Option B (Redis Cluster chart, 3 masters + 3 replicas by default): `values.yaml` uses image `bitnamilegacy/redis-cluster:8.2.1-debian-12-r0`, an `initContainers` entry copying `/var/lib/falkordb/bin/falkordb.so` from `falkordb/falkordb-server:latest` into an `emptyDir` mounted at `/falkordbmodule/`, and `configmap: loadmodule /falkordbmodule/falkordb.so`; install with `helm upgrade falkordb oci://registry-1.docker.io/bitnamicharts/redis-cluster --values values.yaml --install`. Bitnami charts enable PVCs by default (`master.persistence.size`, `replica.persistence.size`); scale with `replica.replicaCount`.

### 3.4 KubeBlocks ([kubeblocks](https://docs.falkordb.com/operations/kubeblocks.md))
Requires K8s ≥ 1.21, kubectl, helm.
```bash
helm repo add kubeblocks https://apecloud.github.io/helm-charts
helm repo update
helm install kubeblocks kubeblocks/kubeblocks --namespace kb-system --create-namespace
curl -fsSL https://kubeblocks.io/installer/install_cli.sh | bash
kbcli addon install falkordb          # or: helm install falkordb-addon kubeblocks-addons/falkordb
kubectl create namespace demo
```
Topologies (`apps.kubeblocks.io/v1` `Cluster`, `clusterDef: falkordb`): `standalone`; `replication` (components `falkordb` replicas 2 + `falkordb-sent` Sentinel replicas 3, `serviceVersion: "4.12.5"`, Sentinel starts first); `sharding` (3 shards, `componentDef: falkordb-cluster-4`). Examples use 0.5 CPU / 0.5Gi / 20Gi PVC. Password: `kubectl get secret -n demo falkordb-replication-conn-credential -o jsonpath='{.data.password}' | base64 -d`. Day-2 via `OpsRequest` (HorizontalScaling, VerticalScaling, VolumeExpansion, Restart, Reconfiguring, Expose). Backups: `BackupRepo` (S3), `Backup` with `backupMethod: datafile` (BGSAVE/RDB), PITR via AOF (`aof-timestamp-enabled yes` + enable `aof` method on the BackupSchedule); restore via annotation `kubeblocks.io/restore-from-backup`. Delete: patch `terminationPolicy` to `WipeOut` (deletes backups too) then `kubectl delete cluster`.

### 3.5 Railway ([railway](https://docs.falkordb.com/operations/railway.md))
Two verified templates: Single Instance (`railway.com/deploy/falkordb-1`, Browser on by default) and Cluster (`railway.com/deploy/falkordb-cluster`). Variables: `FALKORDB_PASSWORD`, `FALKORDB_PRIVATE_URL` (same project/environment only), `FALKORDB_PUBLIC_URL` (needs Railway TCP Proxy), `FALKORDB_HOST`, `FALKORDB_PORT`, `RAILWAY_PUBLIC_DOMAIN` (Browser; login user `default`).
```bash
redis-cli -u "$FALKORDB_PUBLIC_URL" GRAPH.QUERY mygraph "RETURN 'connected' AS status"
redis-cli -c -u "$FALKORDB_PRIVATE_URL"      # cluster template
```
Python: `FalkorDB.from_url(os.environ["FALKORDB_PRIVATE_URL"])` (cluster mode auto-detected). Template provides persistent Railway volumes; "persistence is not a replacement for backups" — configure Railway volume backups; without a volume data is lost on redeploy. Deploy time "under 2 minutes".

### 3.6 Lightning.AI, OpenTelemetry
- [Lightning.AI](https://docs.falkordb.com/operations/lightning-ai.md): a hosted notebook "environment" with a preconfigured FalkorDB; for prototyping, not production (page says so).
- [OpenTelemetry](https://docs.falkordb.com/operations/opentelemetry.md): Python 3.9+; `pip install falkordb opentelemetry-distro opentelemetry-instrumentation-redis opentelemetry-exporter-otlp opentelemetry-sdk`; manual spans around `g.query(...)` with `db.system=falkordb`; exporters Console / OTLP (`http://localhost:4317`) / Jaeger. Tracing is client-side; no server metrics endpoint documented here.

---
## 4. FalkorDBLite (embedded)

Pages: [index](https://docs.falkordb.com/operations/falkordblite/index.md), [Python](https://docs.falkordb.com/operations/falkordblite/falkordblite-py.md), [TypeScript](https://docs.falkordb.com/operations/falkordblite/falkordblite-ts.md). Bundles Redis + FalkorDB module as an embedded process managed by your app; intended for dev, tests, CI, demos — **docs say not for production / multi-user** (Python FAQ; index).

| | Python | TypeScript |
|---|---|---|
| Install | `pip install falkordblite` (deps `redis>=4.5`, `psutil`) | `npm install falkordblite` (`npm install falkordb` for the remote client) |
| Runtime | Python ≥ 3.12 | Node.js ≥ 20 |
| Platforms | macOS needs `brew install libomp`; Linux/Windows support **not documented** | Linux x64 and macOS arm64 only; Windows → WSL2 or remote server; module downloaded during `npm install` |
| Persistence | pass a db file path: `FalkorDB('/tmp/falkordb.db')`; reopen same path to keep data; no path = temp dir, may be lost | `FalkorDB.open({ path: '/tmp/falkordb-lite' })` enables periodic snapshots; default = temp dir |
| Import | `from redislite.falkordb_client import FalkorDB`; also `from redislite import Redis` for KV | `import { FalkorDB } from 'falkordblite'` |

Python API shown: `db.select_graph('social')`, `g.query(...)`, `g.ro_query(...)`, `g.delete()`, `db.list_graphs()`, `result.result_set`. Data is localhost-only and user-private ("secure default Redis configuration").
TS API: `await FalkorDB.open(opts)`, `db.selectGraph(name)`, `graph.query`, `graph.roQuery`, `result.data`, `await db.close()`. Options table: `path` (temp dir), `redisServerPath`, `modulePath`, `maxMemory` (e.g. `"256mb"`), `logLevel`, `logFile`, `timeout` (10000 ms), `additionalConfig` (extra redis.conf, e.g. `{ port: '6379' }`), `falkordbVersion` (default `v4.16.3`), `inheritStdio`. Migrating to a server = swap to `FalkorDB.connect({ socket: { host, port } })` from package `falkordb`.
Limits/not documented: max data size, concurrency model, durability guarantees (AOF vs RDB), Python platform matrix, Python path-arg semantics beyond the examples. [INFERENCE: FalkorDBLite TS pins module v4.16.3 by default — compare with the server version you target.]

---
## 5. Migration guides

Index: [migration](https://docs.falkordb.com/operations/migration/index.md). None of the guides contains a Cypher/syntax difference table; they only say "most standard queries work; Neo4j-specific functions or APOC procedures may need alternatives" ([neo4j](https://docs.falkordb.com/operations/migration/neo4j-to-falkordb.md)). Authoritative differences live in `/cypher/cypher-support` and `/cypher/known-limitations` (other parts).

### 5.1 RedisGraph → FalkorDB ([guide](https://docs.falkordb.com/operations/migration/redisgraph-to-falkordb.md))
- RedisGraph EOL 31 Jan 2025; FalkorDB is the successor, same `GRAPH.*` command API (`GRAPH.QUERY/RO_QUERY/EXPLAIN/PROFILE/DELETE/LIST`), same GraphBLAS engine, **loads RedisGraph RDB files unchanged** (no conversion).
- Steps: on RedisGraph `redis-cli` → `SAVE` (blocking) or `BGSAVE`; copy `dump.rdb`; then
```bash
docker run -it -p 6379:6379 -v $(pwd):/data -e REDIS_ARGS="--dir /data --dbfilename dump.rdb" falkordb/falkordb
```
Verify with `GRAPH.LIST` and `GRAPH.QUERY your_graph_name "MATCH (n) RETURN count(n)"`.
- RedisGraph-era community clients are "not officially tested or supported"; use official FalkorDB clients. Cloud: "follow the cloud provider's instructions" (see §7.5 for RDB import).
- Added over RedisGraph: vector indexes, centrality/community/flow algorithms, UDFs, GraphRAG SDK, Browser.

### 5.2 Neo4j → FalkorDB ([guide](https://docs.falkordb.com/operations/migration/neo4j-to-falkordb.md))
CSV pipeline using `github.com/FalkorDB/Neo4j-to-FalkorDB` (Python 3.9+): (1) analyze/template: `python3 neo4j_to_csv_extractor.py --password <pw> --generate-template <t>.json --analyze-only`; (2) edit `migrate_config.json` (labels/properties mapping); (3) extract: `python3 neo4j_to_csv_extractor.py --password <pw> --config migrate_config.json` → `csv_output/` with `nodes_<label>.csv`, `edges_<type>.csv`, `indexes.csv`, `constraints.csv`, `load_to_falkordb.cypher`, `create_indexes_falkordb.cypher`. Options: `--uri` (default `bolt://localhost:7687`), `--username`, `--database`, `--batch-size`, `--nodes-only/--edges-only/--indexes-only`, `--tenant-mode {label,property}` + `--tenant-filter`. (4) load: `python3 falkordb_csv_loader.py MOVIES --port 6379 --stats` (options `--host --port --username --password --batch-size 5000 --csv-dir --merge-mode --multi-graph`), or the Rust loader `FalkorDB-Loader-RS` (`cargo build --release`, `./target/release/falkordb-loader MOVIES --host … --batch-size 1000 --merge-mode --stats --progress-interval 500`; recommended for large data). Loader auto-creates `CREATE INDEX ON :Label(id)` ID indexes plus indexes/constraints from the CSVs. (5) validate with equivalent queries in both DBs; indexes check: `GRAPH.QUERY mygraph 'CALL db.indexes()'`.

### 5.3 Kuzu ([guide](https://docs.falkordb.com/operations/migration/kuzu-to-falkordb.md))
`pip3 install kuzu`; `git clone https://github.com/FalkorDB/Kuzu-to-FalkorDB`; `python3 kuzu_to_falkordb_export.py --db path/to/db [--schema schema.json] [--output csv_output]`; CSV layout nodes `id,labels,props…`, edges `source,source_label,target,target_label,type`; then Rust loader as above. The script remaps some relationship names and enhances labels (e.g. `Application:Process`) — a data-shape difference to watch.

### 5.4 RDF/TTL ([guide](https://docs.falkordb.com/operations/migration/rdf-to-falkordb.md))
`git clone https://github.com/FalkorDB/rdf-to-falkordb`; `python3 rdf_to_csv_extractor.py import/x.ttl --extract-ontology config/x.json` → review config → `python3 rdf_to_csv_extractor.py import/x.ttl --config config/x.json --shorten-uris --output-dir out --csv-output-peek` → `python3 falkordb_csv_loader.py <graph> --csv-dir out --merge-mode --stats` (or Rust loader). Triples become properties or relationships per the ontology config; optional `--uri-prefixes` JSON.

### 5.5 SQL → graph, continuous sync ([guide](https://docs.falkordb.com/operations/migration/sql-to-falkordb.md))
`github.com/FalkorDB/DM-SQL-to-FalkorDB` (Rust CLIs + optional web control plane on `:3003`). Sources: BigQuery, ClickHouse, Databricks, MariaDB, MySQL, Oracle, PostgreSQL, Snowflake, Spark SQL (Livy), SQL Server. Declarative YAML/JSON mappings, `UNWIND`+`MERGE` idempotent writes, incremental watermarks, CDC for MySQL/MariaDB (binlog), Oracle (LogMiner), Postgres (logical replication), Snowflake (Streams). Example: `cargo run --release -- --config postgres.yaml [--daemon --interval-secs 60] [--purge-graph] [--introspect-schema] [--generate-template --output t.yaml]`. Databricks and Spark are one-shot only; Postgres has no purge flags. FalkorDB endpoint form: `falkor://127.0.0.1:6379`.

---
## 6. Docker/ops facts worth remembering for FalkorDB core
(See §1–3.) Single-primary replication does not fail over by itself; cluster shards by graph, not within a graph; ACL users need `aclfile` + `ACL SAVE`; `falkordb-server` is the production image.

---
## 7. FalkorDB Cloud (managed)

Overview: [cloud/index](https://docs.falkordb.com/cloud/index.md), [features](https://docs.falkordb.com/cloud/features.md). Console `app.falkordb.cloud`; Cloud API is **beta** (endpoints may change) ([index](https://docs.falkordb.com/cloud/index.md)).

### 7.1 Tiers
| Tier | Tenancy / price | RAM | TLS | Backups | Persistence | HA | Support |
|---|---|---|---|---|---|---|---|
| Free | multi-tenant, $0 | **100 MB** (max dataset 100 MB), AWS or GCP | no | **none** (no snapshots either) | **none** | no | community |
| Startup | multi-tenant, from $73/mo ($0.100 per GB-hour; 1 GB = $73, 2 GB = $146) | from 1 GB, dataset ≈75 % of RAM | yes | every 12 h, kept 7 d | not continuous | no (standalone only) | community |
| Pro | dedicated, from $350/mo ($0.200/core-h + $0.01/GB-h; 2 core/8 GB standalone ≈ $350.40) | from 8 GB | yes | every 12 h, kept 7 d | continuous (AOF+snapshot) | yes (replicated; single/multi-zone; +2 cores/2 GB Sentinel overhead) | 24/7 |
| Enterprise | dedicated, custom; BYOA in own AWS account | custom | yes | every 2 h, kept 2 d | continuous | yes + clusters, VPC/customer networks, advanced monitoring, Azure, maintenance windows | dedicated |
Sources: [free](https://docs.falkordb.com/cloud/tiers/free.md), [startup](https://docs.falkordb.com/cloud/tiers/startup.md), [pro](https://docs.falkordb.com/cloud/tiers/pro.md), [enterprise](https://docs.falkordb.com/cloud/tiers/enterprise.md). All tiers: multi-graph tenancy and graph access control.
- **[CONFLICT]** Pro "from 8 GB" in the comparison table vs. pricing tables that list a 4 GB (2 core) standalone row ($321.20/mo) — [pro](https://docs.falkordb.com/cloud/tiers/pro.md).
- **Free-tier lifecycle**: "Free instances that aren't utilized for **1 day will be stopped, and deleted after 7 days**. No persistence and no backups. A deleted instance and its data cannot be recovered." ([free](https://docs.falkordb.com/cloud/tiers/free.md)). Extensions via sales.
- Paid tiers: stopped instance is removed after **14 days** (snapshot taken first, restorable for 14 d); all snapshots auto-deleted after 14 d ([startup](https://docs.falkordb.com/cloud/tiers/startup.md), [create-instance](https://docs.falkordb.com/cloud/console/create-instance.md)).

### 7.2 Create ([create-instance](https://docs.falkordb.com/cloud/console/create-instance.md), [sign-up](https://docs.falkordb.com/cloud/console/sign-up.md))
Sign up (email/GitHub/Google) → Subscribe (Free/Startup/Pro auto-approved; Enterprise needs approval) → **Deployments > Instances > Create** → pick plan, deployment type (Standalone; Single-Zone/Multi-Zone on Pro+; Cluster-* on Enterprise; **cannot change later**), provider/region (AWS/GCP; Azure on Enterprise), FalkorDB user (default `falkordb`) and password (≥ 6 chars). **Cannot be changed after creation:** Enable TLS, FalkorDB user, persistence, tuning options (cache size, result-set size). Modify can change name, description, password, and (paid tiers) size. Delete requires typing `deleteme`; optional final snapshot on paid tiers. Roles: Root/Admin/Editor/Reader. Free needs no card; paid needs a Stripe payment method ([billing](https://docs.falkordb.com/cloud/console/billing.md)).

### 7.3 Connect & TLS ([connect](https://docs.falkordb.com/cloud/console/connect.md), [quickstart](https://docs.falkordb.com/cloud/quickstart.md))
Endpoint = `host:port` from the **Connectivity** tab (port is often not 6379); user/password from **Instance Details**. **Free instances do not use TLS**; on paid tiers add `--tls` / `ssl=True` / `tls: true` iff Enable TLS was set (TLS is "required" when on — [features](https://docs.falkordb.com/cloud/features.md)).
```bash
redis-cli -h <host> -p <port> --user falkordb --pass "$FALKORDB_PASSWORD" \
  GRAPH.QUERY social "CREATE (:Person {name: 'Alice'}) RETURN 1"
```
```python
from falkordb import FalkorDB
db = FalkorDB(host="<host>", port=<port>, username="falkordb", password="<password>", ssl=True)
```
```js
const db = await FalkorDB.connect({ username: "falkordb", password: "<password>", socket: { host: "<host>", port: <port>, tls: true } });
```
Browser: **Connect** button opens FalkorDB Browser prefilled (disabled for private instances). Private (Enterprise customer network, CIDR ≥ /20, peering via support ticket) instances have no public endpoint ([customer-networks](https://docs.falkordb.com/cloud/operations/customer-networks.md)). API quickstart: sign in via `POST https://app.falkordb.cloud/api/signin` (session cookie `omnistrate_token`, lasts 1 h), create via `api.omnistrate.cloud` (see [quickstart](https://docs.falkordb.com/cloud/quickstart.md)); poll until `status` = `RUNNING`; `result_params` holds host/port.

### 7.4 Users ([user-management](https://docs.falkordb.com/cloud/operations/user-management.md))
User Access tab: default user cannot be deleted/renamed; roles `Admin`, `Read` (GRAPH.RO_QUERY/EXPLAIN/INFO/LIST, DUMP…), `Write` (+GRAPH.QUERY/DELETE/BULK/COPY/UDF…), or `Custom` (key patterns like `~*` + command list). Metrics dashboard (Grafana) on Startup+ except BYOA ([monitoring-dashboard](https://docs.falkordb.com/cloud/operations/monitoring-dashboard.md)).

### 7.5 Backups, export/import ([backups-snapshots](https://docs.falkordb.com/cloud/operations/backups-snapshots.md), [export-import](https://docs.falkordb.com/cloud/operations/export-import.md))
Restore always creates a **new** instance (also point-in-time restore, UTC). Snapshots can be taken any time (paid tiers), copied across regions. RDB export: temp link (valid 1 h), GCS, or S3. RDB import: file upload (≤ **2 GB**), HTTPS URL, GCS, S3, or another instance; **import erases the target first** (safety copy taken). One task at a time per instance. Scheduled exports Pro/Enterprise only (≥ 60 min, multiple of 15, max 2 schedules, auto-disabled after 3 failures). Free-tier data can only be kept via manual RDB export.
Upgrading/changing tier or deployment type = new instance + "import from another instance" ([upgrading-instances](https://docs.falkordb.com/cloud/operations/upgrading-instances.md)). Maintenance windows (Enterprise: ≤ 4 h, Sun–Wed 6:00–20:00 UTC; others get advance notice only) — [maintenance-windows](https://docs.falkordb.com/cloud/operations/maintenance-windows.md).

---
## 8. FalkorDB Enterprise (self-managed on Kubernetes) — summary

~55 pages ([index](https://docs.falkordb.com/enterprise/index.md), [overview](https://docs.falkordb.com/enterprise/get-started/overview.md)). Enterprise is a Helm-delivered distribution: Admin UI + Admin Server (REST), FalkorDB KubeBlocks addon, Browser, `falkordb-admin` CLI, `install.sh`/`uninstall.sh`. Topologies: standalone, replicated, replicated+Sentinel, sharded. Install: `curl -fsSL https://falkordb.github.io/FalkorDB-Enterprise/install.sh | bash -s -- --registry-username '<u>' --registry-password '<token>'` ([quickstart](https://docs.falkordb.com/enterprise/get-started/quickstart.md)); images/chart come from private `registry.falkordb.cloud`, credentials and licenses via the [Enterprise Portal](https://docs.falkordb.com/enterprise/get-started/enterprise-portal.md). Needs ≥ 3 workers (4 CPU/16 GB each), default CSI StorageClass, K8s ≥ 1.27 recommended; one install per cluster ([requirements](https://docs.falkordb.com/enterprise/get-started/requirements.md)). A 14-day trial starts automatically; licenses limit capacity only (deployments, CPU, memory, users), not features ([licensing](https://docs.falkordb.com/enterprise/licensing.md)). Platform guides: AKS (+private/internal LB), EKS, GKE, K3s, OpenShift, Rancher; OAuth with Google / Entra ID; TLS, external DNS, scaling, graph offloading to disk, backups to S3/GCS/Azure/MinIO/NFS/PVC (default repo is in-cluster PVC — not safe for production), RDB export/import, Prometheus/Grafana monitoring, Pod Security `restricted` and Cosign-signed images in 1.0 (beta) ([backups](https://docs.falkordb.com/enterprise/operations/backups.md), [1.0 notes](https://docs.falkordb.com/enterprise/releases/1-0.md)). Not relevant to a hackathon demo; pointers only.

---
## 9. Ops checklist — hackathon demo that must survive weeks unattended  **[ALL INFERENCE]**
Built from the pages above; none of this is stated as a single recipe in the docs.

1. **Persistence on, verified.** `REDIS_ARGS="--appendonly yes --appendfsync everysec"` (+ default RDB `save` rules) ([durability](https://docs.falkordb.com/operations/durability/index.md)); named volume on the data dir. Because docs disagree on `/data` vs `/var/lib/falkordb/data` (§1), run `redis-cli CONFIG GET dir` and mount that. Test: create data → `docker restart` → `docker rm -f` + recreate → data still there ([persistence](https://docs.falkordb.com/operations/durability/persistence.md)). Never run `docker compose down -v`.
2. **Pin the image tag**, not `latest` — use `falkordb/falkordb-server:<tag>` (the docs' own advice, [docker](https://docs.falkordb.com/operations/docker.md)). Current tag names are not given in these pages; read Docker Hub.
3. **Password + non-default ACL user.** `--requirepass` or `--aclfile` with `ACL SAVE`, then `ACL SETUSER default off` after an admin exists ([acl-persistence](https://docs.falkordb.com/operations/durability/acl-persistence.md)). Keep the password in `.env`, not the compose file. Don't publish 6379 publicly (`expose:` or bind to 127.0.0.1).
4. **Healthcheck with auth** (`redis-cli -a $PASSWORD ping`; docs' interval 30 s, retries 5, `start_period` 30 s) and `restart: unless-stopped` ([docker](https://docs.falkordb.com/operations/docker.md)). A `ping` check proves Redis is up, not that the module is loaded — also consider `GRAPH.LIST` as the test command.
5. **Memory.** Set a container memory limit and `--maxmemory` clearly below it (RDB fork / AOF rewrite need headroom — docs mention fork overhead). **Do not copy `--maxmemory-policy allkeys-lru` from the docs' production example**: it lets Redis evict whole graph keys under pressure, i.e. silently delete a demo graph. `noeviction` is the safer choice for a data store; writes fail instead of data vanishing. (Policy choice is my inference; the docs only list `allkeys-lru` as an example.)
6. **Log rotation:** `json-file` `max-size: 10m`, `max-file: 3` ([docker](https://docs.falkordb.com/operations/docker.md)) so weeks of logs don't fill disk.
7. **Reseed on start.** Keep a deterministic seed script outside the DB; at app/container start, check `GRAPH.LIST` / a count query and re-run seed if the graph is missing (idempotent `MERGE`, as the SQL loaders do — [sql-to-falkordb](https://docs.falkordb.com/operations/migration/sql-to-falkordb.md)). Protects against volume loss, Free-Cloud expiry, eviction.
8. **Backups.** Periodic `BGSAVE` and copy `dump.rdb` (+AOF dir) off the host, test a restore ([durability](https://docs.falkordb.com/operations/durability/index.md)); per-graph `DUMP` is available but the documented CLI redirect looks lossy (§2.4). Cloud equivalents: RDB export to S3/GCS, scheduled on Pro+ ([export-import](https://docs.falkordb.com/cloud/operations/export-import.md)).
9. **Monitor persistence:** `INFO persistence` → `aof_last_rewrite_status`, `rdb_last_save_time`; disk free space.
10. **Don't use** FalkorDBLite (docs: not for production), Lightning.AI (prototype), or **Cloud Free** (stops after 1 idle day, deleted after 7, no backups) for a weeks-long unattended demo. Cloud Startup ($73/mo, 1 GB, daily-ish backups) is the cheapest managed tier that survives idleness; Free works only if something touches it daily and a reseed script exists ([free](https://docs.falkordb.com/cloud/tiers/free.md)).
11. **Graph size sanity:** Cloud Free = 100 MB total dataset; plan seed size accordingly ([free](https://docs.falkordb.com/cloud/tiers/free.md)).
12. **Windows host note:** docs' commands use bash (`$(pwd)`, `for i in {1..6}`, `sudo tee /etc/hosts`); run in git-bash/WSL2. Docker Desktop bind-mount path quirks are not documented.

Pages read: 95 (10 operations, 6 migration, 3 durability, 3 FalkorDBLite, 18 cloud, 55 enterprise [skimmed: index, overview, quickstart, requirements, licensing, backups, offloading, 1.0 notes, compatibility, portal; rest by title/description]).
