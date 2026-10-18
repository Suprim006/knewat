"""Backend registry: ``open_backend(spec)`` returns a ready :class:`CoordinationBackend` for an arm."""

from __future__ import annotations

from collections.abc import Callable

from knewat.crucible.api import BackendSpec, CoordinationBackend

ARMS = ("B0", "B1", "B2", "P")
ALL_ARMS = (*ARMS, "P-mcp")


_EXTRA: dict[str, Callable[[BackendSpec], CoordinationBackend]] = {}


def register_arm(name: str, factory: Callable[[BackendSpec], CoordinationBackend] | None) -> None:
    """Add (or, with ``None``, remove) an arm. Used by the tests to check that the harness catches broken arms."""
    if factory is None:
        _EXTRA.pop(name, None)
    else:
        _EXTRA[name] = factory


def open_backend(spec: BackendSpec) -> CoordinationBackend:
    """Open (creating if needed) the tenant store for ``spec.arm``. Cheap enough to call per process/thread."""
    if spec.arm in _EXTRA:
        return _EXTRA[spec.arm](spec)
    if spec.arm == "B0":
        from knewat.crucible.backends.files import FilesBackend

        return FilesBackend(spec.tenant, spec.root)
    if spec.arm == "B1":
        from knewat.crucible.backends.sqlite import SqliteBackend

        return SqliteBackend(spec.tenant, spec.root)
    if spec.arm == "B2":
        from knewat.crucible.backends.vector import VectorBackend

        return VectorBackend(spec.tenant, spec.root, spec.embedder)
    if spec.arm in ("P", "P-mcp"):
        from knewat.crucible.backends.knewat import KnewatBackend

        return KnewatBackend(
            spec.tenant,
            host=spec.host or None,
            port=spec.port or None,
            embedder=spec.embedder,
            mode="service" if spec.arm == "P" else "mcp",
        )
    raise ValueError(f"unknown arm '{spec.arm}' (expected one of {', '.join(ALL_ARMS)})")
