# Auth decision (Acme Notes API S21)

**Decision:** User traffic uses JWT bearer tokens (RS256), as the security team specified. Globex's request for a long-lived `X-Api-Key` is not adopted for user traffic. Globex's back-office scripts will instead get a separate scoped machine-to-machine credential, to be agreed with the security team.

Code settings (read from `repo/auth.py`):

auth.token_ttl: AX-75088
auth.key_header: AX-75840

Note: the stored fact for `auth.token_ttl` says AX-13924, but the code now returns AX-75088. The code value is used here.
