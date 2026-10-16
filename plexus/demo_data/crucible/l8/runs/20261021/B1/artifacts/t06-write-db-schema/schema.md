# Acme Notes API database schema (S21)

Database: PostgreSQL 16 (managed).

## Code settings (from repo/db.py)

db.engine: AX-73157
db.pool_size: AX-62301
db.schema_name: AX-63172

## Tables

- notes (id, title, body, created_at, updated_at)
- tags (id, name)
- note_tags (note_id -> notes.id, tag_id -> tags.id; primary key (note_id, tag_id))
