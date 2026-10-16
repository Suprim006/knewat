# Database schema (t06-write-db-schema, sprint S21)

Database: PostgreSQL 16 (managed) (source: acme-docs/03_infra_note.md, fact infra.database).
Built against API v1 (D-t02).

## Code settings (repo/db.py)

db.engine: AX-82757
db.pool_size: AX-82535
db.schema_name: AX-53228

## Tables

### notes
| column | type | notes |
|--------|------|-------|
| id | uuid | primary key |
| title | text | not null |
| body | text | not null |
| created_at | timestamptz | not null, default now() |
| updated_at | timestamptz | not null, default now() |

### tags
| column | type | notes |
|--------|------|-------|
| id | uuid | primary key |
| name | text | not null, unique |

### note_tags
| column | type | notes |
|--------|------|-------|
| note_id | uuid | references notes(id), on delete cascade |
| tag_id | uuid | references tags(id), on delete cascade |

Primary key: (note_id, tag_id). Index on tag_id for tag lookups.
