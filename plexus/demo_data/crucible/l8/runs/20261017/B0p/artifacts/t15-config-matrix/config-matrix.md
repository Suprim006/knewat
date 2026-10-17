# Configuration matrix (Acme Notes API, sprint S21)

Built against: API v2 (style guide), PostgreSQL 16. Values read from the current code in `repo/`.

config.region: AX-49629
config.secret_store: AX-85001
config.env_name: AX-28152
db.pool_size: AX-82535
db.replica_count: AX-86955
auth.hash_rounds: AX-15064
auth.mfa_window: AX-33950
ratelimit.window: AX-72602

Note: `auth.hash_rounds` in current code is AX-15064; memory/facts.md (t04) had AX-13975, which is stale.
