"""Crucible Layer 3 (pilot): the real three-agent team on each arm's backend.

The same unmodified ``claude -p`` agents, role prompts, tool names and scheduler of the P3 demo run once per arm;
only the MCP server behind the ``knewat`` name changes:

* ``P``      the real ``knewat-mcp`` over the tenant graph (exactly the P3 real run);
* ``B0/B1``  :mod:`knewat.crucible.l3.baseline_mcp`, a stdio MCP server with the *same tool names and argument
  names* as the Knewat tools the scenario uses, backed by the file or SQLite backend of Layer 1/2.

:mod:`knewat.crucible.l3.run` drives the runs and writes the ``L3`` layer. See ``docs`` in that module for what was
and was not run.
"""
