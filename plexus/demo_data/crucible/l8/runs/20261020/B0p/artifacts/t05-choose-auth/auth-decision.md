# Authentication decision (t05-choose-auth)

User traffic uses JWT bearer tokens (RS256, 15-minute expiry) per the security note. Globex's request for a long-lived `X-Api-Key` key is not adopted for user traffic; it is deferred to a security-reviewed machine-to-machine follow-up.

auth.token_ttl: AX-70256
auth.key_header: AX-73094
