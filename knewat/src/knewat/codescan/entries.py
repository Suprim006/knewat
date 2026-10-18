# ruff: noqa: E501  (long prose lines, as in mcp/ and cli.py)
"""Turn file contents into ``mark_changed`` entries: one file-level entry, plus one per Python symbol.

Every symbol of a parseable Python file is sent (new and deleted ones), not only the changed ones. That keeps the
server from treating a file-level change as covering symbols the client has just told it did not change (a file-level
change covers the symbol anchors of a file only when the batch has no symbol entries for it). The cost is one
``CodeAnchor`` per symbol of every file seen; a file with more than ``MAX_SYMBOLS_PER_FILE`` symbols is reported at
file level only.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from knewat.codescan.hashing import hash_bytes, python_symbols

MAX_ENTRIES = 200  # mark_changed accepts at most this many entries per call
MAX_SYMBOLS_PER_FILE = MAX_ENTRIES - 10
PYTHON_SUFFIXES = (".py", ".pyi")


def file_entries(
    path: str, new: bytes | None, old: bytes | None = None, *, symbols: bool = True
) -> list[dict[str, Any]]:
    """Entries for one file. ``path`` is canonical; ``new`` / ``old`` are the contents (``None`` = absent).

    ``new is None`` means the file is gone (``new_hash=''``). With ``old=None`` the entries carry no
    ``old_hash``: the server compares against the hash it has stored (or records a baseline).
    """
    out: list[dict[str, Any]] = [
        {
            "path": path,
            "new_hash": "" if new is None else hash_bytes(new),
            "old_hash": "" if old is None else hash_bytes(old),
        }
    ]
    if not (symbols and path.lower().endswith(PYTHON_SUFFIXES)):
        return out
    new_syms = [] if new is None else python_symbols(new)
    old_syms = [] if old is None else (python_symbols(old) or [])
    if new_syms is None:  # does not parse right now (a half-typed edit): file level only
        return out
    now = {s.name: s for s in new_syms}
    before = {s.name: s for s in old_syms}
    names = list(dict.fromkeys([*now, *before]))
    if len(names) > MAX_SYMBOLS_PER_FILE:
        return out
    for name in names:
        n, o = now.get(name), before.get(name)
        out.append(
            {
                "path": path,
                "symbol": name,
                "kind": (n or o).kind,  # type: ignore[union-attr]
                "new_hash": n.hash if n else "",
                "old_hash": o.hash if o else "",
            }
        )
    return out


def chunk_entries(
    groups: Iterable[list[dict[str, Any]]], size: int = MAX_ENTRIES
) -> Iterator[list[dict[str, Any]]]:
    """Pack per-file entry groups into calls of at most ``size`` entries, never splitting a file.

    A group larger than ``size`` is cut to its file-level entry (always first).
    """
    batch: list[dict[str, Any]] = []
    for group in groups:
        if len(group) > size:
            group = group[:1]
        if batch and len(batch) + len(group) > size:
            yield batch
            batch = []
        batch.extend(group)
    if batch:
        yield batch
