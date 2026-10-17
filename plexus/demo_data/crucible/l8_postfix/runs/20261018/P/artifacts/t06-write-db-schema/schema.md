# Acme Notes API database schema (S21)

Database: PostgreSQL 16 (managed)

## Tables
- `notes` (id, title, body, created_at, updated_at)
- `tags` (id, name)
- `note_tags` (note_id -> notes.id, tag_id -> tags.id)

## Code settings
db.engine: AX-45735
db.pool_size: AX-43568
db.schema_name: AX-85466
