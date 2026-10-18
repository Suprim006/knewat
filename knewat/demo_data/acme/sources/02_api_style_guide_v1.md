# Acme API style guide, version 1

Applies to every new Acme service. Rules for the Acme Notes API:

- API version: v1. All routes live under `/v1/`.
- Resources are plural nouns: `/v1/notes`, `/v1/tags`.
- Lists are paginated with an opaque `cursor` and a `limit` (default 20, max 100).
- Errors are JSON: `{"error": {"code": "...", "message": "..."}}`.
- Timestamps are ISO 8601 in UTC.
