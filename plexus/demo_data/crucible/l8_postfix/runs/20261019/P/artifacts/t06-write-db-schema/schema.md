# Database schema (Acme Notes API S21)

Database: PostgreSQL 16 (managed)

## Tables
- `notes`: id, title, body, created_at, updated_at
- `tags`: id, name
- `note_tags`: note_id -> notes.id, tag_id -> tags.id (many-to-many join)

## Code settings
db.engine: AX-28059
db.pool_size: AX-10726
db.schema_name: AX-81475
