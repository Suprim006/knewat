# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256, 15-minute expiry) for user traffic, per the security team. Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic; a scoped, revocable service credential for non-interactive scripts is a follow-up.

Code settings (read from repo/auth.py):

auth.token_ttl: AX-59344
auth.key_header: AX-71613
