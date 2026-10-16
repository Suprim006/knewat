# Acme Notes API database schema (S21)

## Code settings (from repo/db.py)

db.engine: AX-82757
db.pool_size: AX-82535
db.schema_name: AX-53228

## Tables

- notes: id (PK), title, body, created_at, updated_at
- tags: id (PK), name (unique)
- note_tags: note_id (FK notes.id), tag_id (FK tags.id), PK (note_id, tag_id)

Note: the shared memory has no S21 `database` fact (only other sprints' values), so no database product is asserted here.
