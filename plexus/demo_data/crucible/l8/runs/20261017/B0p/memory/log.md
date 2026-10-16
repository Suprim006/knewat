# Log (sprint S21)

- builder, t03-design-endpoints: building against API v1 (D-t02). Will draft endpoints list/create/read/update/delete notes under base path AX-25930.
- researcher, t06-write-db-schema (taking over from interrupted builder): team runs PostgreSQL 16 (managed). Creating tables notes (id, title, body, timestamps), tags (id, unique name) and note_tags (note_id, tag_id join table, composite PK) in schema AX-53228.
- researcher, ingest-v2: style_guide.api_version changed from v1 to v2 (new guide acme-docs/06_api_style_guide_v2.md supersedes v1; routes under /v2/, page_token/page_size, RFC 9457 errors).
- builder, t12-update-endpoints-for-v2: building against API v2 (D-t02-v2). Endpoint design changes: (1) routes move under /v2/ (/v2/notes, /v2/notes/{id}); (2) list pagination uses page_token/page_size; (3) errors use RFC 9457 problem details instead of v1 api.error_format; (4) auth unchanged (JWT, D-t05). Code settings re-read: api.base_path = AX-25930, api.cors_origin = AX-79535.
