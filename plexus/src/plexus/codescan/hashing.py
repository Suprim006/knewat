# ruff: noqa: E501  (long prose lines, as in mcp/ and cli.py)
"""Content hashes for files and for Python symbols (functions, classes, methods).

Hashes are sha256 hex digests. Line endings are normalised first (CRLF -> LF), so a Windows checkout and a Linux one
hash the same. A symbol's hash covers its source (decorators included), de-indented and stripped of trailing
whitespace, so moving a function elsewhere in the file, or indenting its class differently, does not change it;
renaming it, or editing any character of its body, does.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass


def normalize_bytes(data: bytes) -> bytes:
    """CRLF -> LF."""
    return data.replace(b"\r\n", b"\n")


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(normalize_bytes(data)).hexdigest()


@dataclass(frozen=True)
class Symbol:
    name: str  # dotted qualname: 'PaymentService.create'
    kind: str  # 'function' (methods too) | 'class'
    hash: str


def _segment(lines: list[str], node: ast.AST) -> str:
    start = min([d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno])  # type: ignore[attr-defined]
    end = node.end_lineno or node.lineno  # type: ignore[attr-defined]
    col = node.col_offset  # type: ignore[attr-defined]
    out: list[str] = []
    for line in lines[start - 1 : end]:
        head = line[:col]
        out.append((line[col:] if not head.strip() else line).rstrip())
    return "\n".join(out).strip("\n")


def python_symbols(source: bytes | str) -> list[Symbol] | None:
    """Top-level functions and classes, and the methods of classes, with dotted qualnames.

    ``None`` when the source does not parse (a half-typed edit): callers then fall back to file level only.
    Definitions that share a qualname (a property and its setter) are hashed together, in file order.
    """
    data = source.encode() if isinstance(source, str) else source
    try:
        text = normalize_bytes(data).decode("utf-8-sig")
        tree = ast.parse(text)
    except (SyntaxError, ValueError, UnicodeDecodeError):
        return None
    lines = text.split("\n")
    found: dict[str, tuple[str, list[str]]] = {}

    def walk(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                kind = "function"
            elif isinstance(node, ast.ClassDef):
                kind = "class"
            else:
                continue
            name = prefix + node.name
            found.setdefault(name, (kind, []))[1].append(_segment(lines, node))
            if isinstance(node, ast.ClassDef):
                walk(node.body, name + ".")

    walk(tree.body, "")
    return [
        Symbol(name, kind, hashlib.sha256("\n\n".join(segs).encode()).hexdigest())
        for name, (kind, segs) in found.items()
    ]
