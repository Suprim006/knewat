# Release notes (Acme Notes API, S21)

Release channel used in sprint S20: general availability

## Settings

api.base_path: AX-63003
auth.token_ttl: AX-65554
db.engine: AX-73157
billing.cycle: AX-82972
billing.currency: AX-53118
config.region: AX-49725
config.secret_store: AX-83924
config.env_name: AX-23213
db.pool_size: AX-62301
db.replica_count: AX-10016
auth.hash_rounds: AX-60445
auth.mfa_window: AX-11418
ratelimit.window: AX-12377

Notes: values are read from the code under repo/ (api.py, auth.py, db.py, billing.py, config.py, ratelimit.py). config.secret_store is not defined in repo/config.py; its value comes from the configuration matrix (artifacts/t15-config-matrix/config-matrix.md).
