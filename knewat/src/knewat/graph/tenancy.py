"""Tenant -> graph name mapping. One FalkorDB graph per tenant; tests use throwaway graphs."""

from __future__ import annotations

import re
import uuid

TENANT_PREFIX = "knewat_t_"
_TENANT_RE = re.compile(r"[a-z0-9_]{1,48}")


def graph_name(tenant: str) -> str:
    """``knewat_t_<tenant>``; tenant must match ``^[a-z0-9_]{1,48}$`` (no case folding, no whitespace)."""
    if not isinstance(tenant, str) or _TENANT_RE.fullmatch(tenant) is None:
        raise ValueError(f"invalid tenant {tenant!r}: must match ^[a-z0-9_]{{1,48}}$")
    return f"{TENANT_PREFIX}{tenant}"


def test_graph_name() -> str:
    """A unique throwaway graph name, ``test_<uuid hex>``."""
    return f"test_{uuid.uuid4().hex}"


# Not a test: stop pytest collecting the helper when it is imported into a test module.
test_graph_name.__test__ = False  # type: ignore[attr-defined]
