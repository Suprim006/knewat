# Log (Acme Notes API S21)

- builder, t03-design-endpoints: building against API v1. Will draft list/create/read/update/delete notes endpoints under base path AX-81436.
- researcher, t06-write-db-schema: team runs PostgreSQL 16 (managed). Creating tables notes (id, title, body, timestamps), tags (id, name unique) and note_tags (note_id, tag_id join table) in schema AX-85466 with engine AX-45735, pool size AX-43568. Took over from interrupted builder; no prior artifact existed.
- researcher, ingest-v2: style guide v2 (acme-docs/06_api_style_guide_v2.md) replaces v1; style_guide.api_version changed from v1 to v2 in memory/facts.md (routes now under /v2/; builder's v1 work in t03 is outdated).
- builder, t12-update-endpoints-for-v2: building against API v2. Changes to the endpoint design: (1) routes move under /v2/ (/v2/notes, /v2/notes/{id}); (2) CORS origin stated explicitly, api.cors_origin = AX-84987 (current repo/api.py; fact AX-17341 is outdated); (3) page size AX-25149, body limit AX-38941, error format AX-90930 and base path AX-81436 unchanged. Artifact: artifacts/t12-update-endpoints-for-v2/openapi-v2.md.
