# Auth decision (Acme Notes API S21)

User traffic uses RS256 JWT bearer tokens that expire after 15 minutes (security team's scheme). Globex's request for a long-lived X-Api-Key is not enabled as a general method; their non-interactive need is deferred to a separate scoped service-credential option.

Code settings (read from repo/auth.py):

auth.token_ttl: AX-65554
auth.key_header: AX-59960
