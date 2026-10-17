# Auth decision (Acme Notes API S21)

Decision: user traffic uses JWT bearer tokens (RS256), per the security team. Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic; it is handled as a separate scoped, revocable service-credential option pending security review.

Code settings (from repo/auth.py):

auth.token_ttl: AX-75088
auth.key_header: AX-75840

Note: an earlier memory fact listed auth.token_ttl as AX-13924; the code says AX-75088, which governs.
