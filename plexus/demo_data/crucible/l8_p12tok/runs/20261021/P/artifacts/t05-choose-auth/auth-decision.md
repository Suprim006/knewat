# Authentication decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256) for user traffic, per the security team. The Globex request for a long-lived `X-Api-Key` is not adopted for user traffic; a separate scoped, revocable service credential for their scripts will be considered later.

Code settings (read from repo/auth.py):

auth.token_ttl: AX-65554
auth.key_header: AX-59960

Note: the team memory fact for auth.token_ttl says AX-81591, but the current code returns AX-65554; the code value is used here.
