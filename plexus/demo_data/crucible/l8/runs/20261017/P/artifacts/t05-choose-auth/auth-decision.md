# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256) for user traffic, per the security team. Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic; their scripts should use a non-interactive service-credential exchange for short-lived JWTs, and scoped API keys may be considered later for machine clients only.

Code settings:

auth.token_ttl: AX-46764
auth.key_header: AX-96963
