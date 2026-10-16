# Database schema (Acme Notes API S21, t06-write-db-schema)

Database: PostgreSQL 16 (managed) (source: acme-docs/03_infra_note.md, via memory/facts.md). API version: v1.

## Code settings (source: repo/db.py)

db.engine: AX-73157
db.pool_size: AX-62301
db.schema_name: AX-63172

## Tables

### notes
- id: uuid, primary key
- title: text, not null
- body: text, not null
- created_at: timestamptz, not null
- updated_at: timestamptz, not null

### tags
- id: uuid, primary key
- name: text, not null, unique

### note_tags
- note_id: uuid, not null, references notes(id) on delete cascade
- tag_id: uuid, not null, references tags(id) on delete cascade
- primary key (note_id, tag_id)
