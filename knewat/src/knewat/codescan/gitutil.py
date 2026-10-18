"""Thin, bounded wrappers around the ``git`` command line (the client runs on the developer machine)."""

from __future__ import annotations

import subprocess
from pathlib import Path

GIT_TIMEOUT_S = 10.0


class GitError(RuntimeError):
    pass


def run_git(repo: str | Path, *args: str, timeout: float = GIT_TIMEOUT_S, check: bool = True) -> bytes:
    try:
        p = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo), *args],  # noqa: S607
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {args[0]} timed out after {timeout}s") from exc
    if check and p.returncode != 0:
        raise GitError(f"git {' '.join(args[:3])} failed: {p.stderr.decode(errors='replace').strip()[:200]}")
    return p.stdout if p.returncode == 0 else b""


def toplevel(directory: str | Path) -> str | None:
    """The repository root containing ``directory``, or ``None`` when it is not in a git work tree."""
    try:
        out = run_git(directory, "rev-parse", "--show-toplevel", timeout=3.0, check=False)
    except GitError:
        return None
    return out.decode().strip() or None


def show_file(repo: str | Path, ref: str, relpath: str) -> bytes | None:
    """The file's content at ``ref`` (``git show ref:path``), or ``None`` when it does not exist there."""
    try:
        p = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo), "show", f"{ref}:{relpath}"],  # noqa: S607
            capture_output=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return p.stdout if p.returncode == 0 else None


def has_parent(repo: str | Path, ref: str) -> bool:
    return bool(run_git(repo, "rev-parse", "--verify", "--quiet", f"{ref}~1", check=False).strip())


def commit_info(repo: str | Path, ref: str) -> tuple[str, int]:
    """``(full commit hash, commit time in epoch ms)``."""
    out = run_git(repo, "show", "-s", "--format=%H %ct", ref).decode().split()
    return out[0], int(out[1]) * 1000


def changed_paths(repo: str | Path, ref: str) -> list[str]:
    """Repo-relative paths added, modified or deleted by commit ``ref`` (renames count as delete + add)."""
    if has_parent(repo, ref):
        out = run_git(repo, "diff", "--name-only", "--no-renames", "-z", f"{ref}~1", ref)
    else:
        out = run_git(repo, "show", "--pretty=format:", "--name-only", "--no-renames", "-z", ref)
    return [p for p in out.decode("utf-8", errors="replace").split("\0") if p.strip()]
