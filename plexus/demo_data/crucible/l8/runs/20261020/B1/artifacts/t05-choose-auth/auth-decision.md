# Authentication decision (S21)

Decision: JWT bearer tokens (RS256) for user traffic, per the security team. Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic; non-interactive Globex scripts will get a scoped, revocable machine credential exchanged for a short-lived JWT.

Code settings (from repo/auth.py):

auth.token_ttl: AX-70256
auth.key_header: AX-73094
