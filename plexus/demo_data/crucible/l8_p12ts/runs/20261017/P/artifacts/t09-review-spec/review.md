# Review of the Acme Notes API S21 spec

Decision: REJECTED until the mismatches below are reconciled.

Code settings (read from repo/):

api.base_path: AX-25930
auth.token_ttl: AX-92098
db.engine: AX-50215

Findings:
- api_version is v2 in memory; consistent.
- api.base_path matches memory (AX-25930).
- auth.token_ttl: code AX-92098, memory AX-46764. Mismatch.
- db.engine: code AX-50215, memory AX-82757. Mismatch.
- auth_method has two conflicting S21 facts (JWT bearer RS256 vs API key in X-Api-Key header).
