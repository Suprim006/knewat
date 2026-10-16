# Database schema (Acme Notes API S21, t06-write-db-schema)

Database: PostgreSQL 16 (managed) [source: acme-docs/03_infra_note.md, fact infra.database].

## Code settings (source: repo/db.py, agrees with memory/facts.md)

db.engine: AX-14196
db.pool_size: AX-52276
db.schema_name: AX-76631

## Tables

### notes
- id: uuid, primary key
- title: text, not null
- body: text, not null
- created_at: timestamptz, not null, default now()
- updated_at: timestamptz, not null, default now()

### tags
- id: uuid, primary key
- name: text, not null, unique

### note_tags
- note_id: uuid, not null, foreign key to notes(id), on delete cascade
- tag_id: uuid, not null, foreign key to tags(id), on delete cascade
- primary key (note_id, tag_id)

All tables live in the schema named by db.schema_name.
