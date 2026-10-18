# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256, 15 minute expiry) for user traffic, per the security note.
Globex's request for a long-lived X-Api-Key is not adopted as the general scheme. Their back-office scripts
get a follow-up: a scoped, revocable service credential exchanged for short-lived JWTs.

Code settings (read from repo/auth.py):

auth.token_ttl: AX-59344
auth.key_header: AX-71613
