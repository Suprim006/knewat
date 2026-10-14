"""Backend registry: ``open_backend(spec)`` returns a ready :class:`CoordinationBackend` for an arm."""

from __future__ import annotations

from plexus.crucible.api import BackendSpec, CoordinationBackend

ARMS = ("B0", "B1", "B2", "P")
ALL_ARMS = (*ARMS, "P-mcp")
LABELS = {"B0": "Files", "B1": "SQLite", "B2": "Vector", "P": "Plexus", "P-mcp": "Plexus (MCP path)"}


def open_backend(spec: BackendSpec) -> CoordinationBackend:
    """Open (creating if needed) the tenant store for ``spec.arm``. Cheap enough to call per process/thread."""
    if spec.arm == "B0":
        from plexus.crucible.backends.files import FilesBackend

        return FilesBackend(spec.tenant, spec.root)
    if spec.arm == "B1":
        from plexus.crucible.backends.sqlite import SqliteBackend

        return SqliteBackend(spec.tenant, spec.root)
    if spec.arm == "B2":
        from plexus.crucible.backends.vector import VectorBackend

        return VectorBackend(spec.tenant, spec.root, spec.embedder)
    if spec.arm in ("P", "P-mcp"):
        from plexus.crucible.backends.plexus import PlexusBackend

        return PlexusBackend(
            spec.tenant,
            host=spec.host or None,
            port=spec.port or None,
            embedder=spec.embedder,
            mode="service" if spec.arm == "P" else "mcp",
        )
    raise ValueError(f"unknown arm '{spec.arm}' (expected one of {', '.join(ALL_ARMS)})")
