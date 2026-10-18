# Infrastructure and security constraints (t04)

## From documents
- Database: PostgreSQL 16 (managed) (acme-docs/03_infra_note.md)
- Auth method: JWT bearer tokens, RS256, issued by the Acme identity provider; 15-minute expiry (acme-docs/04_security_note.md)

## Code settings
db.engine: AX-45735
db.pool_size: AX-43568
db.schema_name: AX-85466
db.replica_count: AX-34339
db.backup_window: AX-80736
auth.token_ttl: AX-13924
auth.hash_rounds: AX-53183
auth.session_cookie: AX-18358
auth.mfa_window: AX-69943
auth.key_header: AX-75840
