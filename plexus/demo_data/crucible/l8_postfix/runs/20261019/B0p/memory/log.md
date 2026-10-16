# Log (sprint S21)

- t03-design-endpoints (builder): building against API v1, base path AX-80684. Will draft endpoints: list, create, read, update, delete notes under the base path.
- t06-write-db-schema (researcher, finishing builder's interrupted work): PostgreSQL 16. Tables: notes (id, title, body, created_at, updated_at), tags (id, name unique), note_tags (note_id, tag_id join table, composite PK, cascade FKs).
- ingest-v2 (researcher): style guide v2 (acme-docs/06_api_style_guide_v2.md) supersedes v1; style_guide.api_version changed from v1 to v2 in memory/facts.md.
- t12-update-endpoints-for-v2 (builder): changes to endpoint design: (1) version label v1 -> v2; (2) api.base_path stays AX-80684 and api.cors_origin is AX-13629 (both re-checked in repo/api.py); (3) five notes endpoints (list, create, read, update, delete) kept under the base path, auth stays JWT bearer (D-t05); (4) api.error_format mismatch (code AX-41106 vs facts AX-55709) still open.
