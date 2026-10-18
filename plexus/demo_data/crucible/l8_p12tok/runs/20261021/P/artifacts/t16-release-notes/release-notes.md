# Release notes (Acme Notes API S21)

Settings relied on by the review, the billing plan and the configuration matrix:

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

Note: all values were read from `repo/*.py`, except `config.secret_store`, which is not defined in `repo/config.py` and is taken from the t15 configuration matrix.

## Release channel

The release channel used in sprint S20 was: general availability.
