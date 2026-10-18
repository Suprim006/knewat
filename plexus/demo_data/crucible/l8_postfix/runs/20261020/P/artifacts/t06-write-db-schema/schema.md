# Database schema (Acme Notes API S21)

Database: PostgreSQL 16 (managed)

## Tables
- notes: id, title, body, created_at, updated_at
- tags: id, name
- note_tags: note_id -> notes.id, tag_id -> tags.id (many-to-many)

## Code settings
db.engine: AX-14196
db.pool_size: AX-52276
db.schema_name: AX-76631
