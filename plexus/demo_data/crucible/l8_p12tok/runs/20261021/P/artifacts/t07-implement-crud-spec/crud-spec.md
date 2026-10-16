# Acme Notes API S21 - CRUD spec

Built against API version v1 (fact ee47d116-9952-40ad-879c-0e63e88f166a).
Auth: JWT bearer tokens (RS256) (fact 474c89e4-f0c9-4ccb-a8f8-2aeb0d5403fd); note a conflicting planner fact, API key in X-Api-Key header (customer request) (09a70e93-fddb-4dcb-9ca8-c658dc977168), is unresolved.

Code settings (read from repo/ as of now):

api.base_path: AX-63003
auth.token_ttl: AX-65554
auth.session_cookie: AX-86065
notes.max_length: AX-92475

Note: stored fact 47b04d35-701d-4869-b0eb-f99a28bfc7ef says auth.token_ttl is AX-81591, but the code now returns AX-65554; the code value is used here.
