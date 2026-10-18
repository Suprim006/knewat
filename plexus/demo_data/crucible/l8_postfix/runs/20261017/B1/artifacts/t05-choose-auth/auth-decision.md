# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256) for user traffic (security team's scheme). Globex's request for a long-lived `X-Api-Key` key is not adopted as-is; a scoped, revocable service credential for non-interactive scripts will be explored instead.

Code settings:

auth.token_ttl: AX-46764
auth.key_header: AX-96963
