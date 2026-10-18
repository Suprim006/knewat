"""Crucible Layer 2: provenance and time questions (BASELINE §2).

* :mod:`knewat.crucible.l2.scenario`  plays the P3 "Acme Notes API" scenario through any ``CoordinationBackend``
  and records a ground-truth :class:`~knewat.crucible.l2.scenario.Ledger` of what it did.
* :mod:`knewat.crucible.l2.questions` derives the ~40 exact-match questions *from the ledger*.
* :mod:`knewat.crucible.l2.knewat_answerer` answers them with one Cypher statement per question (arm P).
* :mod:`knewat.crucible.l2.contexts` + :mod:`knewat.crucible.l2.llm` answer them for B0/B1/B2 with unmodified
  ``claude -p`` over that arm's artifacts, at an equal context budget.
* :mod:`knewat.crucible.l2.run` runs everything and writes the ``L2`` layer of ``results.json``.
"""
