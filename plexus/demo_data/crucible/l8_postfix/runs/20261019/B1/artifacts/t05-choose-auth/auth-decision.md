# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256) for user traffic (security team's scheme). Globex's request for a long-lived `X-Api-Key` is not adopted; a scoped, short-lived service-token option is a follow-up for their non-interactive scripts.

Code settings (read from repo/auth.py):

auth.token_ttl: AX-59344
auth.key_header: AX-71613

Note: memory holds a fact auth.token_ttl = AX-87187 that differs from the current code (AX-59344); the code value is reported here.
