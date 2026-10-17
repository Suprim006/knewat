# Release notes (Acme Notes API S21)

Values below were re-read from the current `repo/` code. Two differ from earlier artifacts: `billing.cycle` and `billing.currency` changed since t13 (AX-14962 / AX-86465), so the current code values are used.

## Code settings

api.base_path: AX-80684
auth.token_ttl: AX-59344
db.engine: AX-28059
billing.cycle: AX-42079
billing.currency: AX-87484
config.region: AX-49787
config.secret_store: AX-24118
config.env_name: AX-89720
db.pool_size: AX-10726
db.replica_count: AX-48545
auth.hash_rounds: AX-52301
auth.mfa_window: AX-50544
ratelimit.window: AX-94252

## Release channel

The team's S20 release channel was general availability (source: history/MEMORY.md, Acme Notes API S20 release_channel).

## Sources

- repo/api.py, repo/auth.py, repo/db.py, repo/billing.py, repo/config.py, repo/ratelimit.py
- Earlier values superseded: auth.token_ttl AX-87187, auth.mfa_window AX-37780, ratelimit.window AX-34064 (S03 note), billing.cycle AX-14962, billing.currency AX-86465.
