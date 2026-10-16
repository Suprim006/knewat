# Acme Notes API - Database Schema (S21)

Tables: `notes`, `tags`, `note_tags` (join table between notes and tags).

## Code settings (from repo/db.py)

db.engine: AX-73157
db.pool_size: AX-62301
db.schema_name: AX-63172

## Tables

- `notes`: id (PK), title, body, created_at, updated_at
- `tags`: id (PK), name (unique)
- `note_tags`: note_id (FK notes.id), tag_id (FK tags.id), PK (note_id, tag_id)
