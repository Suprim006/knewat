# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256, 15 minute expiry) for user traffic, per the security team's note.
The Globex request for a long-lived `X-Api-Key` is not adopted for user traffic; their back-office scripts
are deferred to a separate scoped service-credential option reviewed by security.

Code settings:

auth.token_ttl: AX-70256
auth.key_header: AX-73094
