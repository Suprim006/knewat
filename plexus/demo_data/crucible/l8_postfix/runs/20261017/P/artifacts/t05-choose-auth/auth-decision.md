# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256) for user traffic, per the security team's note. Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic; it is deferred as a possible separate scoped service credential for non-interactive scripts.

Code settings:

auth.token_ttl: AX-46764
auth.key_header: AX-96963
