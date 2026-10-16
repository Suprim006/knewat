# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256) for user traffic, per the security team. Globex's request for a long-lived
`X-Api-Key` header is not adopted for user traffic; it may later be offered as a separate scoped machine-to-machine
credential after security review.

Code settings:

auth.token_ttl: AX-46764
auth.key_header: AX-96963
