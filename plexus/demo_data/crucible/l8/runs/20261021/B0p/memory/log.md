# Log (Acme Notes API S21)

- builder, t03-design-endpoints: building against API version v1. Drafting endpoints under base path AX-63003: list, create, read, update, delete notes.
- researcher, t06-write-db-schema: finishing builder's interrupted task (no partial artifact found). Database is PostgreSQL 16; creating tables notes, tags, note_tags (many-to-many join) under schema AX-63172, engine AX-73157, pool size AX-62301.
- builder, t12-update-endpoints-for-v2: building against API v2. Endpoint design changes from v1: routes move under /v2/; list pagination uses page_token/page_size; errors become RFC 9457 problem details; settings re-read from repo/api.py: api.base_path = AX-63003, api.cors_origin = AX-94293.
- researcher, ingest-v2: style guide v2 (acme-docs/06_api_style_guide_v2.md) replaces v1; product.api_version changed from v1 to v2 (routes under /v2/, page_token/page_size pagination, RFC 9457 errors).
