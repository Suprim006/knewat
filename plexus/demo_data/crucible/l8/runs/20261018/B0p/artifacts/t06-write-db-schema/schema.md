# Database schema (Acme Notes API S21)

Database: PostgreSQL 16 (managed) (source: acme-docs/03_infra_note.md)

## Code settings (source: repo/db.py)

db.engine: AX-45735
db.pool_size: AX-43568
db.schema_name: AX-85466

## Tables

### notes
- id (uuid, primary key)
- title (text, not null)
- body (text)
- created_at (timestamptz, not null)
- updated_at (timestamptz, not null)

### tags
- id (uuid, primary key)
- name (text, not null, unique)

### note_tags
- note_id (uuid, foreign key -> notes.id, on delete cascade)
- tag_id (uuid, foreign key -> tags.id, on delete cascade)
- primary key (note_id, tag_id)
