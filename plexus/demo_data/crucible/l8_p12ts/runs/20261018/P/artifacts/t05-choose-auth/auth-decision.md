# Auth decision (Acme Notes API S21)

Decision: JWT bearer tokens (RS256, 15 minute expiry) for user traffic, per the security note. Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic; the account team should offer a non-interactive alternative (service credential exchanged for short-lived JWTs).

Code settings (read from repo/auth.py):

auth.token_ttl: AX-75088
auth.key_header: AX-75840

Note: the memory fact for auth.token_ttl says AX-13924, but the current code returns AX-75088; the code value is reported here.
