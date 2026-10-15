"""The one canonical path form used for ``CodeAnchor.path`` and doc ``Source.uri`` (graph model v1.1).

Canonical = absolute, forward slashes, upper-case drive letter, no ``.``/``..`` segments, no trailing slash::

    C:/Change_folder_after_HDD/physiotherapy/pv-core-api/app/services/payments.py

The functions are pure string handling: the server (a Linux container) must give the same answer for a Windows
path as the client does, and must never resolve a path against its own file system.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re

_DRIVE = re.compile(r"^([A-Za-z]):(?:/|$)")


def canonical_path(path: str) -> str:
    """Normalise an ABSOLUTE ``path`` to the canonical form; ``ValueError`` for an empty or relative one."""
    raw = (path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("path must not be empty")
    m = _DRIVE.match(raw)
    if m:
        drive, rest = m.group(1).upper() + ":", raw[2:]
    elif raw.startswith("/"):
        drive, rest = "", raw
    else:
        raise ValueError(f"path must be absolute (like C:/repo/app.py or /repo/app.py), got '{raw[:80]}'")
    norm = posixpath.normpath("/" + rest.lstrip("/"))  # also collapses '//' and resolves '.' / '..'
    return drive + norm  # the root of a drive stays 'C:/'


def absolute_canonical(path: str, base: str | None = None) -> str:
    """Client side: make ``path`` absolute (relative to ``base`` or the cwd), then canonicalise it."""
    p = path
    if not (_DRIVE.match(p.replace("\\", "/")) or p.startswith(("/", "\\"))):
        p = os.path.join(base or os.getcwd(), p)
    return canonical_path(os.path.abspath(p))


def anchor_id(path: str, symbol: str = "") -> str:
    """Deterministic CodeAnchor id: ``'anc:' + sha1(path#symbol)[:16]`` (``path`` must be canonical)."""
    return "anc:" + hashlib.sha1(f"{path}#{symbol}".encode()).hexdigest()[:16]  # noqa: S324
