"""Crucible L5: staleness (``mark_changed``) and activation forgetting, both deterministic and LLM-free.

``uv run python -m plexus.crucible.l5 run --out plexus/demo_data/crucible/l5`` writes ``<out>/<timestamp>/results.json``
and ``report.md``. The design, hypotheses and pass criteria were pre-registered in ``docs/BASELINE.md`` ("L5
pre-registration") before the first run.
"""

from plexus.crucible.l5.report import render_report, run_all

__all__ = ["render_report", "run_all"]
