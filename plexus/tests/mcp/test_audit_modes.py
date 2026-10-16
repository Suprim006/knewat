"""P9-e: audit modes ``off | light | full`` per tenant / tool class, the per-call ``audit`` argument,
read-only tenants that never create a graph, and a no-write proof (Redis command counters).

Layers: (1) the tool classification and the policy table (no database); (2) the Runtime modes over the
in-memory MCP client; (3) the no-write proof. The guard side is in ``deploy/tests/test_guard.py``.
"""

from __future__ import annotations

import pytest

from plexus.mcp import server as _server  # noqa: F401  (importing registers every tool table)
from plexus.mcp.audit_policy import AuditPolicy
from plexus.mcp.toolkit import ToolTable, all_tool_defs

READ_TOOLS = {
    "recall",
    "fact_history",
    "best_procedure",
    "ready_tasks",
    "task_status",
    "blocked_by_failure",
    "why",
    "why_recalled",
    "who_knew",
    "knew_at",
    "as_of",
    "memory_strength",
    "facts_to_verify",
    "docs_to_update",
}


# ------------------------------------------------------------------------------------ 1. classification
def test_every_tool_has_a_kind_and_the_read_set_is_exactly_the_documented_one():
    defs = {d.name: d for d in all_tool_defs()}
    assert {n for n, d in defs.items() if d.kind == "read"} == READ_TOOLS
    assert {d.kind for d in defs.values()} == {"read", "write"}


def test_only_recall_is_an_exposure_tool():
    assert {d.name for d in all_tool_defs() if d.exposure} == {"recall"}


def test_an_unmarked_tool_is_a_write_tool():
    table = ToolTable()

    @table
    def probe(ts, m, agent_id, step=None):  # pragma: no cover (never run)
        raise AssertionError

    (d,) = list(table)
    assert d.kind == "write" and d.exposure is False


def test_exposure_requires_a_read_tool():
    with pytest.raises(TypeError):
        ToolTable()(kind="write", exposure=True)(lambda ts, m, agent_id, step=None: None)


# ------------------------------------------------------------------------------------ 1b. policy table
def test_default_mode_is_full_and_overrides_match_by_glob_first_wins():
    p = AuditPolicy.from_env({})
    assert p.tenant_mode("anything") == "full"
    p = AuditPolicy.from_env(
        {"PLEXUS_AUDIT_MODE": "light", "PLEXUS_AUDIT_MODES": "demo*=off, team_*=full ,x_*=light"}
    )
    assert p.tenant_mode("demo") == "off" and p.tenant_mode("demo_scripted") == "off"
    assert p.tenant_mode("team_abcd") == "full"
    assert p.tenant_mode("x_1") == "light"
    assert p.tenant_mode("other") == "light"  # the default
    p = AuditPolicy.from_env({"PLEXUS_AUDIT_MODES": "t*=off,team_*=full"})
    assert p.tenant_mode("team_a") == "off"  # first match wins


@pytest.mark.parametrize(
    "env",
    [
        {"PLEXUS_AUDIT_MODE": "loud"},
        {"PLEXUS_AUDIT_MODES": "demo*"},
        {"PLEXUS_AUDIT_MODES": "demo*=quiet"},
        {"PLEXUS_AUDIT_MODES": "=off"},
    ],
)
def test_a_bad_audit_setting_fails_loudly_at_startup(env):
    with pytest.raises(ValueError):
        AuditPolicy.from_env(env)


@pytest.mark.parametrize(
    "tenant_mode,kind,exposure,requested,expected",
    [
        # writes: never lowered, refused (mode off) when the tenant is off
        ("full", "write", False, None, "full"),
        ("light", "write", False, None, "full"),
        ("off", "write", False, None, "off"),
        # meta reads follow the tenant, and a per-call 'light' only lowers
        ("full", "read", False, None, "full"),
        ("full", "read", False, "light", "light"),
        ("light", "read", False, None, "light"),
        ("light", "read", False, "full", "light"),  # never upgrades beyond the tenant mode
        ("off", "read", False, "light", "off"),
        ("off", "read", False, None, "off"),
        # exposure reads (recall): full unless the tenant is off; 'light' may lower it on request
        ("full", "read", True, None, "full"),
        ("light", "read", True, None, "full"),
        ("full", "read", True, "light", "light"),
        ("light", "read", True, "light", "light"),
        ("off", "read", True, None, "off"),
        ("off", "read", True, "light", "off"),
    ],
)
def test_effective_mode_table(tenant_mode, kind, exposure, requested, expected):
    p = AuditPolicy(default=tenant_mode)
    assert p.effective("t", kind, exposure, requested) == expected
