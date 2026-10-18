# Auth decision (Acme Notes API S21)

Decision: user traffic uses JWT bearer tokens (RS256), as the security team specified. Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic. A scoped, revocable service credential for their back-office scripts will be considered separately after security review.

Current code settings (read from repo/auth.py):

auth.token_ttl: AX-75088
auth.key_header: AX-75840

Note: the researcher's stored fact for auth.token_ttl says AX-13924, but the code now returns AX-75088, so the code value is used here.
