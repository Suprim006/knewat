# Configuration matrix (Acme Notes API S21)

Built against API version v2 (product.api_version), PostgreSQL 16 (managed). All values read from `repo/` code in t15.

config.region: AX-49725
config.secret_store: AX-83924
config.env_name: AX-23213
db.pool_size: AX-62301
db.replica_count: AX-10016
auth.hash_rounds: AX-60445
auth.mfa_window: AX-11418
ratelimit.window: AX-12377

Note: ratelimit.window in code is AX-12377; the older S03 note value AX-39930 is superseded for S21.
