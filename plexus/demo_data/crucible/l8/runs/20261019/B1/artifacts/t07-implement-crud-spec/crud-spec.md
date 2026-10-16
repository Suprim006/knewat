# Acme Notes API S21 - CRUD spec

Built against API version v1 (fact 6578a265-80d8-4bb5-ad2e-69258f91b093), auth: JWT bearer tokens RS256 (fact c058f1d3-f48f-4f76-9ef2-4beec4687715).
Setting values below are read from the current code in repo/.

api.base_path: AX-80684
auth.token_ttl: AX-59344
auth.session_cookie: AX-25766
notes.max_length: AX-16383

Note: the memory fact for auth.token_ttl (272218a5-0518-4761-a4f9-e8d76d6f6ceb) says AX-87187, which differs from the code value AX-59344. The code value is used here; the planner should reconcile.
Note: the memory also holds a conflicting auth_method fact (long-lived API key, abea943b-36ef-43d5-a88c-842944298939).
