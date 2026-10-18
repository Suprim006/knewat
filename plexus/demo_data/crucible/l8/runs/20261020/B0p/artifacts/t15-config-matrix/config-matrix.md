# Configuration matrix (Acme Notes API S21)

Values read from the current code in `repo/` (config.py, db.py, auth.py, ratelimit.py).

config.region: AX-50843
config.secret_store: AX-22163
config.env_name: AX-28160
db.pool_size: AX-52276
db.replica_count: AX-36687
auth.hash_rounds: AX-95437
auth.mfa_window: AX-37869
ratelimit.window: AX-80728

Note: ratelimit.window changed since t14 (AX-42266) and the S03 note (AX-37629); AX-80728 is the current code value.
