# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256) govern user traffic (security team's scheme). Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic; their back-office scripts will get a scoped, short-lived service-account token flow instead.

Code settings (from repo/auth.py):

auth.token_ttl: AX-46764
auth.key_header: AX-96963
