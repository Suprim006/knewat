# Release notes (Acme Notes API S21)

Summarises the settings relied on by the review (t09), the billing plan (t13) and the configuration matrix (t15).
Values are read from the current `repo/` code.

## Code settings
api.base_path: AX-18174
auth.token_ttl: AX-62079
db.engine: AX-14196
billing.cycle: AX-86101
billing.currency: AX-86464
config.region: AX-50843
config.secret_store: AX-22163
config.env_name: AX-28160
db.pool_size: AX-52276
db.replica_count: AX-36687
auth.hash_rounds: AX-95437
auth.mfa_window: AX-37869
ratelimit.window: AX-80728

## Notes
- auth.token_ttl: AX-62079 supersedes the earlier AX-70256 (code changed after t04).
- ratelimit.window: AX-80728 supersedes AX-42266 (t14) and the S03 note value AX-37629.

## Release channel
- Sprint S20 release channel: general availability (source: history/MEMORY.md, Acme Notes API S20 release_channel).
