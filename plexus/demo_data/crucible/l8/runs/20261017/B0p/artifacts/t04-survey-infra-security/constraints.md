# Infrastructure and security constraints (S21)

Documents: database is PostgreSQL 16 (managed) (acme-docs/03_infra_note.md); auth is JWT bearer tokens, RS256, 15-minute expiry (acme-docs/04_security_note.md).

Code settings:

db.engine: AX-82757
db.pool_size: AX-82535
db.schema_name: AX-53228
db.replica_count: AX-86955
db.backup_window: AX-33109
auth.token_ttl: AX-46764
auth.hash_rounds: AX-13975
auth.session_cookie: AX-67390
auth.mfa_window: AX-33950
auth.key_header: AX-96963
