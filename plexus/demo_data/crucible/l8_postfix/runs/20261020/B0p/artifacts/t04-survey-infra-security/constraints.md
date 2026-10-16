# Infrastructure and security constraints (t04)

Documents:
- Database: PostgreSQL 16 (managed) [acme-docs/03_infra_note.md]
- Auth method: JWT bearer tokens, RS256, 15 minute expiry [acme-docs/04_security_note.md]

Code settings:

db.engine: AX-14196
db.pool_size: AX-52276
db.schema_name: AX-76631
db.replica_count: AX-36687
db.backup_window: AX-18584
auth.token_ttl: AX-70256
auth.hash_rounds: AX-95437
auth.session_cookie: AX-51120
auth.mfa_window: AX-37869
auth.key_header: AX-73094
