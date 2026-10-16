# Database schema – Acme Notes API (S21)

Tables: `notes`, `tags`, `note_tags` (join table between notes and tags).

- notes(id, title, body, created_at, updated_at)
- tags(id, name)
- note_tags(note_id -> notes.id, tag_id -> tags.id)

Code settings (read from repo/db.py):

db.engine: AX-14196
db.pool_size: AX-52276
db.schema_name: AX-76631
