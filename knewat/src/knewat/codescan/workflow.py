# ruff: noqa: E501  (long prose lines, as in mcp/ and cli.py)
"""The client-side steps behind ``knewat code scan | baseline | hook-run``: collect entries, call the server, report."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from knewat.codescan import gitutil
from knewat.codescan.client import Session
from knewat.codescan.entries import chunk_entries, file_entries
from knewat.codescan.paths import absolute_canonical, canonical_path

MAX_FILE_BYTES = 5_000_000  # larger files are not hashed (generated blobs, databases)
MAX_RESEND = 20  # re-calls of one chunk while the server reports truncated
SKIP_DIRS = (".git/",)


def relpath(repo_root: str, abs_canonical: str) -> str | None:
    """Repo-relative path of a canonical absolute path, or ``None`` when it is outside the repository."""
    root = absolute_canonical(repo_root).rstrip("/") + "/"  # links resolved, like the file paths (P7-06)
    if abs_canonical.lower().startswith(root.lower()):
        return abs_canonical[len(root) :]
    return None


class FileTooLarge(Exception):
    """The file exists but is bigger than ``MAX_FILE_BYTES``: it is not hashed (and is not a deletion)."""


def read_working(abs_path: str) -> bytes | None:
    """The file's bytes now; ``None`` if it does not exist (deleted); ``FileTooLarge`` if it is too big to hash."""
    p = Path(abs_path)
    try:
        if not p.is_file():
            return None
        if p.stat().st_size > MAX_FILE_BYTES:
            raise FileTooLarge(f"{abs_path} is larger than {MAX_FILE_BYTES} bytes")
        return p.read_bytes()
    except OSError:
        return None


def commit_groups(repo: str, ref: str) -> tuple[str, int, list[list[dict[str, Any]]]]:
    """Entries for every file commit ``ref`` changed: ``(commit, commit time ms, per-file entry groups)``.

    Contents come from git (``ref`` and ``ref~1``), not from the working tree, so the answer is about that commit.
    """
    root = gitutil.toplevel(repo) or str(repo)
    commit, at = gitutil.commit_info(root, ref)
    parent = f"{ref}~1" if gitutil.has_parent(root, ref) else None
    groups: list[list[dict[str, Any]]] = []
    real_root = absolute_canonical(
        root
    )  # the repository dir with links resolved; the files are git's own blobs
    for rel in gitutil.changed_paths(root, ref):
        if rel.startswith(SKIP_DIRS):
            continue
        new = gitutil.show_file(root, ref, rel)
        old = gitutil.show_file(root, parent, rel) if parent else None
        groups.append(file_entries(canonical_path(f"{real_root}/{rel}"), new, old))
    return commit, at, groups


def working_groups(repo: str, paths: Iterable[str], *, baseline: bool = False) -> list[list[dict[str, Any]]]:
    """Entries for files as they are on disk now.

    For a scan ``old`` is the committed version (``HEAD``) when the file is in a git work tree; it only matters when
    the server has no hash stored yet, and it lets deleted functions be noticed. A baseline sends no ``old_hash``.
    A file larger than ``MAX_FILE_BYTES`` is skipped with a note on stderr (it is not reported as deleted).
    """
    root = gitutil.toplevel(repo)
    groups: list[list[dict[str, Any]]] = []
    for p in paths:
        cp = absolute_canonical(p, repo)
        old = None
        if root and not baseline:
            rel = relpath(root, cp)
            if rel:
                old = gitutil.show_file(root, "HEAD", rel)
        try:
            new = read_working(cp)
        except FileTooLarge:  # not a deletion: leave the anchor and its facts alone
            print(
                f"knewat code: skipped {cp}: file too large to hash (> {MAX_FILE_BYTES} bytes)",
                file=sys.stderr,
            )
            continue
        groups.append(file_entries(cp, new, old))
    return groups


class Summary:
    """The merged outcome of the ``mark_changed`` calls of one command."""

    def __init__(self) -> None:
        self.calls = 0
        self.entries = 0
        self.changed = 0
        self.suspect_fact_ids: list[str] = []
        self.decisions_total = 0
        self.docs: dict[tuple[str, str], dict[str, Any]] = {}
        self.change_ids: list[str] = []

    def add(self, res: dict[str, Any], entries: int = 0) -> None:
        self.calls += 1
        self.entries += entries
        self.changed += res["changed"]
        for f in res["suspect_fact_ids"]:
            if f not in self.suspect_fact_ids:
                self.suspect_fact_ids.append(f)
        self.decisions_total += res["decisions_total"]
        for d in res["docs_to_update"]:
            self.docs[(d["source_id"], d["anchor"])] = d
        if res["change_id"] and res["change_id"] not in self.change_ids:
            self.change_ids.append(res["change_id"])


async def send(
    s: Session, groups: list[list[dict[str, Any]]], *, commit: str = "", at: int | None = None
) -> Summary:
    """Call ``mark_changed`` for every chunk (continuing while the server says ``truncated``)."""
    out = Summary()
    for chunk in chunk_entries(groups):
        when = at
        for attempt in range(MAX_RESEND):
            args: dict[str, Any] = {"changes": chunk, "commit": commit}
            if when is not None:
                args["at"] = when
            res = await s.call("mark_changed", **args)
            when = res["at"]  # a continuation must use the same event time
            out.add(res, len(chunk) if attempt == 0 else 0)
            if not res["truncated"]:
                break
    return out


async def describe_suspects(s: Session, summary: Summary, limit: int = 50) -> list[dict[str, Any]]:
    """The ``facts_to_verify`` rows of the facts this command made suspect (best effort, the first ``limit``)."""
    if not summary.suspect_fact_ids:
        return []
    rows = (await s.call("facts_to_verify", limit=limit))["facts"]
    wanted = set(summary.suspect_fact_ids)
    return [r for r in rows if r["fact_id"] in wanted]


def fact_line(r: dict[str, Any]) -> str:
    return f"{r['entity']} {r['predicate']}: {r['value']}"


def format_report(title: str, summary: Summary, rows: list[dict[str, Any]]) -> str:
    n = len(summary.suspect_fact_ids)
    lines = [
        f"{title}: {summary.entries} entries sent, {summary.changed} changed, "
        f"{n} {'memory' if n == 1 else 'memories'} may be stale"
    ]
    for r in rows[:10]:
        lines.append(f"  - {fact_line(r)}   [{r['reason']}]")
    if n > len(rows[:10]):
        lines.append(f"  ... and {n - len(rows[:10])} more (facts_to_verify lists them)")
    if summary.decisions_total:
        lines.append(
            f"decisions built on them: {summary.decisions_total} (verify_fact flags them if a fact changed)"
        )
    if summary.docs:
        lines.append("docs to update:")
        for d in sorted(summary.docs.values(), key=lambda d: (d["uri"], d["anchor"]))[:10]:
            lines.append(f"  - {d['uri']}  (describes {d['anchor']})")
    return "\n".join(lines)


def tracked_files(repo: str, tenant: str) -> list[str]:
    """Absolute paths inside ``repo`` with a Source or a CodeAnchor in the tenant's graph (needs FalkorDB access)."""
    from knewat.graph.client import GraphClient
    from knewat.graph.tenancy import graph_name

    client = GraphClient()
    try:
        rows = client.ro(graph_name(tenant), "staleness/tracked_paths", {"limit": 50_000})
    finally:
        client.close()
    root = gitutil.toplevel(repo) or str(repo)
    found: list[str] = []
    for r in rows:
        raw = r["path"] or ""
        if "://" in raw or not raw:
            continue
        try:
            cp = canonical_path(raw)
        except ValueError:
            continue
        if relpath(root, cp) is not None and os.path.isfile(cp) and cp not in found:
            found.append(cp)
    return found
