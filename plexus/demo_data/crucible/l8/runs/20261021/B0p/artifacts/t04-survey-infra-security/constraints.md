# Infrastructure and security constraints (t04)

## From documents
- Database: PostgreSQL 16 (managed) (acme-docs/03_infra_note.md)
- Auth method: JWT bearer tokens, RS256, issued by the Acme identity provider (acme-docs/04_security_note.md)

## Code settings
db.engine: AX-73157
db.pool_size: AX-62301
db.schema_name: AX-63172
db.replica_count: AX-10016
db.backup_window: AX-38796
auth.token_ttl: AX-81591
auth.hash_rounds: AX-60445
auth.session_cookie: AX-86065
auth.mfa_window: AX-11418
auth.key_header: AX-59960
