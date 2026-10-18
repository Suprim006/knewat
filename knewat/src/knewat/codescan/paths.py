"""The one canonical path form used for ``CodeAnchor.path`` and doc ``Source.uri`` (graph model v1.1).

Canonical = absolute, forward slashes, upper-case drive letter, no ``.``/``..`` segments, no trailing slash::

    C:/Change_folder_after_HDD/physiotherapy/pv-core-api/app/services/payments.py

``canonical_path`` is pure string handling: the server (a Linux container) must give the same answer for a
Windows path as the client does, and must never resolve a path against its own file system.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re

_DRIVE = re.compile(r"^([A-Za-z]):(?:/|$)")
_BS = chr(92)  # a backslash
_EXT = _BS * 2 + "?" + _BS  # Windows extended-length prefix
_EXT_UNC = _EXT + "UNC" + _BS


def canonical_path(path: str) -> str:
    """Normalise an ABSOLUTE ``path`` to the canonical form; ``ValueError`` for an empty or relative one.

    A UNC path keeps its host: ``<2 backslashes>server<backslash>share<backslash>a.py`` becomes
    ``//server/share/a.py`` (exactly two leading separators mean UNC; three or more collapse to one). The
    Windows extended prefixes (``<2 backslashes>?<backslash>`` and its ``UNC`` form) are dropped.
    """
    raw = (path or "").strip()
    if raw.upper().startswith(_EXT_UNC):
        raw = _BS * 2 + raw[len(_EXT_UNC) :]
    elif raw.startswith(_EXT):
        raw = raw[len(_EXT) :]
    raw = raw.replace(_BS, "/")
    if not raw:
        raise ValueError("path must not be empty")
    m = _DRIVE.match(raw)
    if m:
        drive, rest = m.group(1).upper() + ":", raw[2:]
    elif raw.startswith("/"):
        drive, rest = "", raw
    else:
        raise ValueError(f"path must be absolute (like C:/repo/app.py or /repo/app.py), got '{raw[:80]}'")
    unc = not drive and raw.startswith("//") and not raw.startswith("///")
    norm = posixpath.normpath("/" + rest.lstrip("/"))  # also collapses '//' and resolves '.' / '..'
    return drive + ("/" if unc else "") + norm  # the root of a drive stays 'C:/'


def absolute_canonical(path: str, base: str | None = None) -> str:
    """Client side: make ``path`` absolute (relative to ``base`` or the cwd), resolve links, canonicalise.

    Symlinks and junctions are resolved (``os.path.realpath``), so a file edited through a linked project
    directory gets the same canonical path as ``git rev-parse --show-toplevel`` reports for it (P7-06).
    A path that does not exist (a deleted file) keeps its last component and resolves the existing parents.
    """
    p = path
    if not (_DRIVE.match(p.replace(_BS, "/")) or p.startswith(("/", _BS))):
        p = os.path.join(base or os.getcwd(), p)
    return canonical_path(os.path.realpath(os.path.abspath(p)))


def anchor_id(path: str, symbol: str = "") -> str:
    """Deterministic CodeAnchor id: ``'anc:' + sha1(path#symbol)[:16]`` (``path`` must be canonical)."""
    return "anc:" + hashlib.sha1(f"{path}#{symbol}".encode()).hexdigest()[:16]  # noqa: S324
