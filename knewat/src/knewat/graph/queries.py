"""Named, parameterised Cypher query library.

Every query the product depends on lives in ``knewat/queries/**/*.cypher`` with a header comment::

    // name: engram/assert_fact
    // purpose: one line on what the query does
    // params: subject_id:str, predicate:str, now:int
    // returns: columns / shape of the result
    // mode: ro|rw
    // split: ;            (optional: the file holds several statements separated by this token)

The query name is the file path relative to the root without the extension (``schema/indexes``). The header
``name`` must match it. Loading is eager and strict: a malformed header, a ``$param`` used in the body but not
declared (or declared but unused), or an invalid mode fails at construction, not at call time.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Mode = Literal["ro", "rw"]

_REQUIRED = ("name", "purpose", "params", "returns", "mode")
_KNOWN = (*_REQUIRED, "split")
_HEADER_LINE = re.compile(r"^//\s?(?P<key>[a-z_]+):\s?(?P<value>.*)$")
_PARAM_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PARAM_REF = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")
_QUERY_NAME = re.compile(r"^[a-z0-9_]+(/[a-z0-9_]+)*$")


class QueryError(Exception):
    """Base class for query-library errors."""


class QueryFormatError(QueryError):
    """A .cypher file has a missing or malformed header, or a body inconsistent with it."""


class UnknownQuery(QueryError, KeyError):
    """No query with that name exists in the library."""

    def __str__(self) -> str:  # KeyError would repr() the message
        return str(self.args[0]) if self.args else ""


class QueryParamError(QueryError, ValueError):
    """Base class for parameter mismatches against a query header."""

    def __init__(self, query: str, names: list[str]):
        self.query = query
        self.names = names
        super().__init__(f"query '{query}': {self._verb} parameter(s) {', '.join(names)}")

    _verb = "bad"


class MissingParam(QueryParamError):
    _verb = "missing"


class UnexpectedParam(QueryParamError):
    _verb = "unexpected"


class ReadOnlyViolation(QueryError, PermissionError):
    """A read-only entry point (``ro``) was asked to run a ``mode: rw`` query."""


class MultiStatementError(QueryError):
    """A query with several statements was run through a single-statement entry point."""


@dataclass(frozen=True)
class Query:
    name: str
    purpose: str
    params: Mapping[str, str]  # param name -> declared type (documentation only)
    returns: str
    mode: Mode
    statements: tuple[str, ...]
    path: Path
    split: str | None = None


@dataclass(frozen=True)
class RenderedQuery:
    """A query checked against caller params, ready to execute."""

    name: str
    mode: Mode
    statements: tuple[str, ...]
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def cypher(self) -> str:
        if len(self.statements) != 1:
            raise MultiStatementError(
                f"query '{self.name}' has {len(self.statements)} statements; use the script entry point"
            )
        return self.statements[0]


def default_queries_root() -> Path:
    override = os.environ.get("KNEWAT_QUERIES_DIR")
    if override:
        return Path(override)
    # src/knewat/graph/queries.py -> knewat/ (project root) / queries
    return Path(__file__).resolve().parents[3] / "queries"


def _split_header(text: str) -> tuple[dict[str, str], list[str]]:
    """Return (header key -> value, remaining body lines)."""
    header: dict[str, str] = {}
    lines = text.splitlines()
    last: str | None = None
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if not raw:
            if header:
                break  # blank line ends the header block
            i += 1
            continue
        if not raw.startswith("//"):
            break
        m = _HEADER_LINE.match(raw)
        if m and m["key"] in _KNOWN:
            key = m["key"]
            if key in header:
                raise QueryFormatError(f"duplicate header key '{key}'")
            # 'split' must keep its raw value (it may be whitespace-sensitive); others are stripped.
            header[key] = m["value"] if key == "split" else m["value"].strip()
            last = key
        elif last is not None and last != "split" and lines[i].startswith("//  "):
            # Indented comment line (`//   more text`) continues the previous value.
            header[last] = (header[last] + " " + raw.lstrip("/").strip()).strip()
        # any other comment line is a free comment: ignored
        i += 1
    return header, lines[i:]


def _parse_params(spec: str) -> dict[str, str]:
    spec = spec.strip()
    if spec.lower() in ("", "none"):
        return {}
    out: dict[str, str] = {}
    # split on commas that are not inside [] (types like list[str])
    parts, depth, cur = [], 0, ""
    for ch in spec:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    for part in parts:
        name, sep, typ = part.partition(":")
        name, typ = name.strip(), typ.strip()
        if not sep or not typ or not _PARAM_NAME.match(name):
            raise QueryFormatError(f"bad param spec '{part.strip()}' (expected name:type)")
        if name in out:
            raise QueryFormatError(f"duplicate param '{name}'")
        out[name] = typ
    return out


def _parse_file(name: str, path: Path) -> Query:
    header, body_lines = _split_header(path.read_text(encoding="utf-8"))
    missing = [k for k in _REQUIRED if k not in header]
    if missing:
        raise QueryFormatError(f"{path}: missing header key(s): {', '.join(missing)}")
    if header["name"] != name:
        raise QueryFormatError(f"{path}: header name '{header['name']}' != path-derived name '{name}'")
    mode = header["mode"]
    if mode not in ("ro", "rw"):
        raise QueryFormatError(f"{path}: mode must be 'ro' or 'rw', got '{mode}'")
    params = _parse_params(header["params"])

    # Drop whole-line comments from the body; they are documentation, not Cypher.
    body = "\n".join(ln for ln in body_lines if not ln.strip().startswith("//")).strip()
    split = header.get("split")
    if split is not None and split.strip() == "":
        raise QueryFormatError(f"{path}: empty split token")
    split = split.strip() if split is not None else None
    chunks = body.split(split) if split else [body]
    statements = tuple(c.strip() for c in chunks if c.strip())
    if not statements:
        raise QueryFormatError(f"{path}: empty query body")

    used = set(_PARAM_REF.findall(body))
    undeclared = sorted(used - params.keys())
    unused = sorted(params.keys() - used)
    if undeclared:
        raise QueryFormatError(f"{path}: body uses undeclared param(s): {', '.join(undeclared)}")
    if unused:
        raise QueryFormatError(f"{path}: header declares unused param(s): {', '.join(unused)}")

    return Query(
        name=name,
        purpose=header["purpose"],
        params=params,
        returns=header["returns"],
        mode=mode,  # type: ignore[arg-type]
        statements=statements,
        path=path,
        split=split,
    )


class QueryLibrary:
    """Loads every ``**/*.cypher`` under ``root`` and validates params at render time."""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else default_queries_root()
        if not self.root.is_dir():
            raise QueryError(f"queries root not found: {self.root}")
        self._queries: dict[str, Query] = {}
        for path in sorted(self.root.rglob("*.cypher")):
            name = path.relative_to(self.root).with_suffix("").as_posix()
            if not _QUERY_NAME.match(name):
                raise QueryFormatError(f"{path}: query name '{name}' must match {_QUERY_NAME.pattern}")
            try:
                self._queries[name] = _parse_file(name, path)
            except QueryFormatError as exc:
                if str(path) in str(exc):
                    raise
                raise QueryFormatError(f"{path}: {exc}") from exc

    def names(self, prefix: str = "") -> list[str]:
        return sorted(n for n in self._queries if n.startswith(prefix))

    def __contains__(self, name: object) -> bool:
        return name in self._queries

    def __iter__(self) -> Iterator[Query]:
        return iter(self._queries[n] for n in sorted(self._queries))

    def __len__(self) -> int:
        return len(self._queries)

    def get(self, name: str) -> Query:
        try:
            return self._queries[name]
        except KeyError:
            raise UnknownQuery(f"unknown query '{name}'") from None

    def render(self, name: str, params: Mapping[str, Any] | None = None) -> RenderedQuery:
        q = self.get(name)
        given = dict(params or {})
        missing = sorted(q.params.keys() - given.keys())
        if missing:
            raise MissingParam(name, missing)
        extra = sorted(given.keys() - q.params.keys())
        if extra:
            raise UnexpectedParam(name, extra)
        return RenderedQuery(name=name, mode=q.mode, statements=q.statements, params=given)
