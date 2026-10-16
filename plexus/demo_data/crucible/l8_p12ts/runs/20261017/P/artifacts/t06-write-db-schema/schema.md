# Database schema (Acme Notes API S21)

Database: PostgreSQL 16

## Tables
- notes: id, title, body, created_at, updated_at
- tags: id, name
- note_tags: note_id -> notes.id, tag_id -> tags.id (join table)

## Code settings
db.engine: AX-82757
db.pool_size: AX-82535
db.schema_name: AX-53228
