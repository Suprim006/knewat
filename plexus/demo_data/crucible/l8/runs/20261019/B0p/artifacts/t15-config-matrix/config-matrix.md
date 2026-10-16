# Configuration matrix (sprint S21)

Built against the current code in `repo/` (read in t15). API version per team facts: v2. Database: PostgreSQL 16 (managed).

config.region: AX-49787
config.secret_store: AX-24118
config.env_name: AX-89720
db.pool_size: AX-10726
db.replica_count: AX-48545
auth.hash_rounds: AX-52301
auth.mfa_window: AX-50544
ratelimit.window: AX-94252

## Notes

- auth.mfa_window changed in code: the t04 survey recorded AX-37780, current code returns AX-50544.
- ratelimit.window: the S03 note said AX-34064 (historical); current code returns AX-94252.
