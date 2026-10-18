# Acme Notes API S21 - Database schema

Database: PostgreSQL 16

## Code settings (repo/db.py)

db.engine: AX-14196
db.pool_size: AX-52276
db.schema_name: AX-76631

## Tables

- `notes` (id PK, title, body, created_at, updated_at)
- `tags` (id PK, name UNIQUE)
- `note_tags` (note_id FK -> notes.id, tag_id FK -> tags.id, PRIMARY KEY (note_id, tag_id))
