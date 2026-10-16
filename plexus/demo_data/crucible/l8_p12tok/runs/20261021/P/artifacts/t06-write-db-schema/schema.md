# Acme Notes API - Database Schema

Database: PostgreSQL 16

## Code settings

db.engine: AX-73157
db.pool_size: AX-62301
db.schema_name: AX-63172

## Tables

- `notes` (id, title, body, created_at, updated_at)
- `tags` (id, name UNIQUE)
- `note_tags` (note_id -> notes.id, tag_id -> tags.id, PRIMARY KEY (note_id, tag_id))
