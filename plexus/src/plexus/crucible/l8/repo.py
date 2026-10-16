"""The L8 repository: the L5a generator with domain names and sentinel tokens, landed one commit at a time.

``crucible/l5/staleness.py`` builds a 12 x 5 function repository and applies all its edit kinds up front. L8 needs the
same files and the same eight edit kinds, but (a) every function returns an opaque sentinel token ``AX-<5 digits>``
(so the scorer can find a fact in any text by string containment), (b) the module and function names are the
domain's (``auth.token_ttl``), and (c) the commits land *during* the run, at scheduled turn boundaries. The
``Module``/``Func`` renderer, the git helper and the ``ast`` ground truth (``segments``) are L5a's, unchanged.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from plexus.crucible.l5.staleness import GIT_BASE_TIME, Func, Module, segments

TOKEN_RE = re.compile(r"AX-\d{5}")

MODULES: dict[str, tuple[str, ...]] = {
    "auth": ("token_ttl", "hash_rounds", "session_cookie", "mfa_window", "key_header"),
    "api": ("base_path", "page_size", "max_body", "cors_origin", "error_format"),
    "db": ("engine", "pool_size", "schema_name", "replica_count", "backup_window"),
    "ratelimit": ("window", "burst", "per_user", "per_key", "retry_after"),
    "notes": ("max_length", "tag_limit", "archive_days", "share_mode", "title_max"),
    "users": ("id_format", "quota_mb", "invite_ttl", "role_default", "locale_default"),
    "search": ("index_name", "analyzer", "max_hits", "fuzzy_level", "refresh_ms"),
    "export": ("format", "max_rows", "signed_url_ttl", "compression", "schedule"),
    "billing": ("cycle", "currency", "grace_days", "invoice_prefix", "tax_mode"),
    "audit": ("retention_days", "sink", "sample_rate", "pii_mask", "event_version"),
    "config": ("region", "feature_flags", "log_level", "env_name", "secret_store"),
    "release": ("channel", "version_tag", "rollout_pct", "freeze_day", "changelog_path"),
}
FUNCS: tuple[tuple[str, str], ...] = tuple((m, f) for m, fs in MODULES.items() for f in fs)
INVALIDATING = ("value", "sibling", "delete")


def key(m: str, f: str) -> str:
    return f"{m}.{f}"


def doc_of(m: str, f: str, k: int = 0) -> str:
    base = f"Setting {m}.{f} of the Acme Notes API (sprint S21)"
    return f"{base}, revised in change {k}." if k else f"{base}."


@dataclass
class Edit:
    """One scheduled change commit (k = 1..10) and what it does, fully determined before any run."""

    k: int
    turn: int  # lands at the boundary before this turn (1-based process index)
    kind: str
    module: str = ""
    funcs: list[str] = field(default_factory=list)  # tracked 'module.function' whose code changes (ground truth)
    new_tokens: dict[str, str] = field(default_factory=dict)  # 'module.function' -> its new token (value/sibling)
    extra: dict[str, Any] = field(default_factory=dict)  # add: name/token; reorder: a/b; whitespace: fn
    biased: bool = False  # the function(s) were drawn from the needs of a task not yet done (nominally)
    forced: str = ""  # why a function was forced in (X3)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Edit:
        return cls(**d)


def initial_modules(tokens: dict[str, str]) -> dict[str, Module]:
    """``tokens``: 'module.function' -> initial token. Values render as string literals ``return "AX-12345"``."""
    return {
        m: Module(m, [Func(f, doc_of(m, f), f'"{tokens[key(m, f)]}"') for f in fs]) for m, fs in MODULES.items()  # type: ignore[arg-type]
    }


def apply_edit(mods: dict[str, Module], e: Edit) -> None:
    """Mutate the module model the way the edit says (the same kinds as L5a, with pre-drawn targets)."""
    mod = mods[e.module]

    def fn(name: str) -> Func:
        return next(f for f in mod.funcs if f.name == name)

    if e.kind in ("value", "sibling"):
        for kf, tok in e.new_tokens.items():
            m, f = kf.split(".", 1)
            next(x for x in mods[m].funcs if x.name == f).value = f'"{tok}"'  # type: ignore[assignment]
    elif e.kind == "docstring":
        f = e.funcs[0].split(".", 1)[1]
        fn(f).doc = doc_of(e.module, f, e.k)
    elif e.kind == "add":
        mod.funcs.append(Func(e.extra["name"], f"Added in change {e.k}.", f'"{e.extra["token"]}"'))  # type: ignore[arg-type]
    elif e.kind == "module-comment":
        mod.comment = f"edited in change {e.k}"
    elif e.kind == "whitespace":
        fn(e.extra["fn"]).trailing = True
    elif e.kind == "reorder":
        a, b = e.extra["a"], e.extra["b"]
        mod.funcs[a], mod.funcs[b] = mod.funcs[b], mod.funcs[a]
    elif e.kind == "delete":
        f = e.funcs[0].split(".", 1)[1]
        mod.funcs = [x for x in mod.funcs if x.name != f]
    else:
        raise ValueError(f"unknown edit kind {e.kind}")


# ------------------------------------------------------------------------------------------------ git
def git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    full = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", **(env or {})}
    r = subprocess.run(
        ["git", "-c", "user.name=l8", "-c", "user.email=l8@example.invalid", "-c", "commit.gpgsign=false",
         "-c", "core.autocrlf=false", *args],
        cwd=root, capture_output=True, text=True, env=full, check=True,
    )  # fmt: skip
    return r.stdout.strip()


def commit(root: Path, message: str, k: int) -> str:
    when = f"{GIT_BASE_TIME + 3600 * k} +0000"
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message, env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
    return git(root, "rev-parse", "HEAD")


def write_modules(root: Path, mods: dict[str, Module], names: list[str] | None = None) -> list[str]:
    """Write the modules whose text differs from disk (or ``names``); return the names written."""
    out = []
    for n in names or sorted(mods):
        p = root / f"{n}.py"
        text = mods[n].render()
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8", newline="\n")
            out.append(n)
    return out


def init_repo(root: Path, mods: dict[str, Module]) -> str:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q")
    write_modules(root, mods)
    return commit(root, "initial", 0)


def ast_truth(root: Path, before: str, after: str) -> set[str]:
    """Tracked functions whose source segment differs between two commits (independent of plexus.codescan)."""
    out: set[str] = set()
    for m in MODULES:
        old = segments(git(root, "show", f"{before}:{m}.py"))
        new = segments(git(root, "show", f"{after}:{m}.py"))
        for f in set(old) | set(new):
            if (m, f) in FUNCS and old.get(f) != new.get(f):
                out.add(key(m, f))
    return out


def land(root: Path, mods: dict[str, Module], e: Edit) -> str:
    """Apply one edit to the model, write the touched module, commit; assert the AST truth equals the script."""
    before = git(root, "rev-parse", "HEAD")
    apply_edit(mods, e)
    if not write_modules(root, mods):
        raise AssertionError(f"change {e.k} ({e.kind}) produced no file change")
    sha = commit(root, f"change {e.k}: {e.kind} in {e.module}", e.k)
    truth = ast_truth(root, before, sha)
    if truth != set(e.funcs if e.kind in ("value", "sibling", "docstring", "delete") else []):
        raise AssertionError(f"change {e.k} {e.kind}: script edits {sorted(e.funcs)} != ast truth {sorted(truth)}")
    return sha
