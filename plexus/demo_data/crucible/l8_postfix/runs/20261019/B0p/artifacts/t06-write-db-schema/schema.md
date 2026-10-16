# Database schema (t06-write-db-schema)

Database: PostgreSQL 16 (source: memory/facts.md, t04-survey-infra-security).

## Code settings (verified against repo/db.py)

db.engine: AX-28059
db.pool_size: AX-10726
db.schema_name: AX-81475

## Tables

### notes
- id: UUID, primary key
- title: text, not null
- body: text, not null
- created_at: timestamptz, not null
- updated_at: timestamptz, not null

### tags
- id: UUID, primary key
- name: text, not null, unique

### note_tags
- note_id: UUID, foreign key to notes(id), on delete cascade
- tag_id: UUID, foreign key to tags(id), on delete cascade
- primary key (note_id, tag_id)
