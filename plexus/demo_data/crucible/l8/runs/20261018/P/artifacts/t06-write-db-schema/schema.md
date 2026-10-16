# Database schema (Acme Notes API, S21)

Settings (read from repo/db.py):

db.engine: AX-45735
db.pool_size: AX-43568
db.schema_name: AX-85466

## Tables

- `notes` (id PK, title, body, created_at, updated_at)
- `tags` (id PK, name UNIQUE)
- `note_tags` (note_id FK -> notes.id, tag_id FK -> tags.id, PK (note_id, tag_id))
