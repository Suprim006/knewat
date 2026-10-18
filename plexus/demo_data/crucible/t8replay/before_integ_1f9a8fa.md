<!-- The same replay script run against the integ tree at 1f9a8fa (before P13): source_ids is silently dropped by the old tool, quarantine/forget ignore other sources. -->
# Trial 8 replay on the multi-source build ($0, scripted)

Memo (C1, C2, C3) and spec (P1, P2 = C1's rule). `quarantine_source(memo)` should hide C2 and C3 and keep C1 and P1.

| scenario | hidden by quarantine(memo) | corroborated (stays visible) | visible after | released | forget(memo): forgotten | unlinked | C1 sources after forget |
|---|---|---|---|---|---|---|---|
| source_ids | C2, C3 | - | C1, P1 | C2, C3 | C2, C3 | - | - |
| corroboration | C1, C2, C3 | - | P1 | C1, C2, C3 | C1, C2, C3 | - | memo, spec |
| single_source | C1, C2, C3 | - | P1 | C1, C2, C3 | C1, C2, C3 | - | memo |

Control (`single_source`) is what the four trial-8 runs wrote: the graph names the memo only, so C1 is hidden.
