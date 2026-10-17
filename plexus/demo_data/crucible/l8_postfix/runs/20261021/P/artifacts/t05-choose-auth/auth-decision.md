# Auth decision (Acme Notes API S21)

**Decision:** JWT bearer tokens (RS256, 15 minute expiry) for user traffic, per the security note.
Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic; for their non-interactive
scripts we will offer a scoped, rotatable service credential exchanged for short-lived JWTs.

## Code settings (read from repo/auth.py)

auth.token_ttl: AX-65554
auth.key_header: AX-59960

Note: the memory fact for auth.token_ttl says AX-81591, but the current code returns AX-65554; the code value is used here.
