# Acme Notes API database schema (S21)

Database: PostgreSQL 16

## Tables
- `notes`: id, title, body, created_at, updated_at
- `tags`: id, name (unique)
- `note_tags`: note_id -> notes.id, tag_id -> tags.id (join table, primary key on both)

## Code settings
db.engine: AX-28059
db.pool_size: AX-10726
db.schema_name: AX-81475
