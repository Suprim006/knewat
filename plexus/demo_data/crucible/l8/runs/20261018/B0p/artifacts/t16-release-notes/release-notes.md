# Release notes (Acme Notes API S21)

Settings relied on by the review (t09), the billing plan (t13) and the configuration matrix (t15). Values re-read from the current `repo/` code.

## Settings

api.base_path: AX-81436
auth.token_ttl: AX-75088
db.engine: AX-45735
billing.cycle: AX-15601
billing.currency: AX-84461
config.region: AX-20369
config.secret_store: AX-72069
config.env_name: AX-39929
db.pool_size: AX-43568
db.replica_count: AX-34339
auth.hash_rounds: AX-53183
auth.mfa_window: AX-69943
ratelimit.window: AX-76589

## Notes

- `auth.token_ttl` is AX-75088 (current code); the older value AX-13924 is superseded.
- `ratelimit.window` is AX-76589 (current S21 code); the S03 note value AX-30896 is outdated.
- Governing API version: v2.

## Release channel

The release channel the team used in sprint S20 was **general availability** (source: history/logs/planner.jsonl, Acme Notes API S20 release_channel).
