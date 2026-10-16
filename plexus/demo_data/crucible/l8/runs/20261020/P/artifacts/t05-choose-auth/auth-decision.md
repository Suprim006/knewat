# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256) for user traffic, per the security team. The Globex request for a long-lived
`X-Api-Key` is not adopted for user traffic; a scoped, revocable machine credential will be explored for their scripts.

Code settings:

auth.token_ttl: AX-70256
auth.key_header: AX-73094
