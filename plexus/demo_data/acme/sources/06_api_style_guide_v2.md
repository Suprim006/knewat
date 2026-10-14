# Acme API style guide, version 2 (supersedes version 1)

Released mid-project. Version 1 is withdrawn. Rules for the Acme Notes API:

- API version: v2. All routes live under `/v2/`; `/v1/` must not be used for new work.
- Resources stay plural nouns: `/v2/notes`, `/v2/tags`.
- Lists use `page_token` and `page_size` (default 25, max 200) instead of `cursor` and `limit`.
- Errors follow RFC 9457 problem details (`application/problem+json`).
- Timestamps are ISO 8601 in UTC.
