# Infrastructure and security constraints (t04)

## From documents
- Database: PostgreSQL 16 (managed) (acme-docs/03_infra_note.md)
- Auth method: JWT bearer tokens, signed with RS256, issued by the Acme identity provider (acme-docs/04_security_note.md)

## Code settings
db.engine: AX-28059
db.pool_size: AX-10726
db.schema_name: AX-81475
db.replica_count: AX-48545
db.backup_window: AX-67698
auth.token_ttl: AX-87187
auth.hash_rounds: AX-52301
auth.session_cookie: AX-25766
auth.mfa_window: AX-37780
auth.key_header: AX-71613
