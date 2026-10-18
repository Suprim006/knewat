"""L5a: does ``mark_changed`` flag exactly the facts whose code changed? (pre-registered in docs/BASELINE.md)

A scripted git repository (12 modules x 5 functions = 60 functions, one initial commit and ``commits`` change commits) and
60 facts, one per function. Three arms, each in its own tenant graph and fed by the real client code
(``knewat.codescan.workflow.commit_groups``):

* ``S``  facts anchored to the function (symbol level), every file and symbol entry is sent;
* ``F``  facts anchored to the file, file-level entries only;
* ``N``  no anchors (the baseline: nothing can be flagged).

The ground truth is computed from the source text with ``ast`` and does not use ``knewat.codescan`` (the script's own edit
log is checked against it). No LLM.
"""

from __future__ import annotations

import ast
import os
import random
import subprocess
import textwrap
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from knewat.codescan.entries import chunk_entries
from knewat.codescan.gitutil import toplevel
from knewat.codescan.hashing import hash_bytes, python_symbols
from knewat.codescan.paths import absolute_canonical
from knewat.codescan.workflow import commit_groups
from knewat.embed import Embedder
from knewat.engram import Engram
from knewat.graph.client import GraphClient
from knewat.graph.schema import apply_schema
from knewat.graph.tenancy import graph_name
from knewat.staleness import Staleness

SEED = 20261016
KINDS = ("value", "sibling", "docstring", "add", "module-comment", "whitespace", "reorder", "delete")
ARMS = ("S", "F", "N")
GIT_BASE_TIME = 1_700_000_000  # commit k happens at base + k hours


# ------------------------------------------------------------------------------------------------ the repository
@dataclass
class Func:
    name: str
    doc: str
    value: int
    trailing: bool = False  # trailing whitespace on the body lines


@dataclass
class Module:
    name: str
    funcs: list[Func] = field(default_factory=list)
    comment: str = "initial"

    def render(self) -> str:
        out = [f'"""Module {self.name}."""', f"# note: {self.comment}", ""]
        for f in self.funcs:
            pad = "  " if f.trailing else ""
            out += ["", f"def {f.name}():", f'    """{f.doc}"""{pad}', f"    return {f.value}{pad}", ""]
        return "\n".join(out) + "\n"


@dataclass
class Commit:
    sha: str
    kind: str
    edited: set[tuple[str, str]]  # (module, function) the script says changed
    truth: set[tuple[str, str]] = field(default_factory=set)  # computed independently from the source text


@dataclass
class Repo:
    root: Path
    modules: dict[str, Module]
    initial: str
    commits: list[Commit]
    facts: list[tuple[str, str, int]]  # (module, function, value at the initial commit)


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    full = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, **(env or {})}
    r = subprocess.run(
        [
            "git",
            "-c",
            "user.name=l5",
            "-c",
            "user.email=l5@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        env=full,
        check=True,
    )
    return r.stdout.strip()


def _commit(root: Path, message: str, k: int) -> str:
    when = f"{GIT_BASE_TIME + 3600 * k} +0000"
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message, env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
    return _git(root, "rev-parse", "HEAD")


def segments(text: str) -> dict[str, str]:
    """Source of every top-level function, independent of ``knewat.codescan``: de-indented, right-stripped."""
    tree = ast.parse(text.replace("\r\n", "\n"))
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            seg = ast.get_source_segment(text.replace("\r\n", "\n"), node) or ""
            out[node.name] = "\n".join(line.rstrip() for line in textwrap.dedent(seg).split("\n")).strip("\n")
    return out


def _order(commits: int, rng: random.Random) -> list[str]:
    """Edit kinds for the change commits: every kind at least once, then the rest drawn at random."""
    kinds = list(KINDS) + [rng.choice(KINDS) for _ in range(max(commits - len(KINDS), 0))]
    kinds = kinds[:commits]
    rng.shuffle(kinds)
    return kinds


def build_repo(root: Path, modules: int = 12, funcs: int = 5, commits: int = 20, seed: int = SEED) -> Repo:
    """Create the scripted repository under ``root`` and return its model, commits and ground truth."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    rng = random.Random(seed)
    mods = {
        f"mod{m:02d}": Module(
            f"mod{m:02d}",
            [Func(f"f{k}", f"Value of mod{m:02d}.f{k}.", 10 * (m + 1) + k) for k in range(funcs)],
        )
        for m in range(modules)
    }

    def write(*names: str) -> None:
        for n in names:
            (root / f"{n}.py").write_text(mods[n].render(), encoding="utf-8", newline="\n")

    write(*mods)
    initial = _commit(root, "initial", 0)
    facts = [(m, f.name, f.value) for m, mod in mods.items() for f in mod.funcs]
    alive = {(m, f.name) for m, mod in mods.items() for f in mod.funcs}
    out: list[Commit] = []
    counter = 1000
    for i, kind in enumerate(_order(commits, rng), start=1):
        edited: set[tuple[str, str]] = set()
        counter += 1
        pick = sorted(alive)
        if kind == "value":
            for m, fn in rng.sample(pick, rng.randint(1, 3)):
                next(f for f in mods[m].funcs if f.name == fn).value = counter + len(edited)
                edited.add((m, fn))
        elif kind == "sibling":
            m = rng.choice(sorted({m for m, _ in pick if sum(1 for x, _ in pick if x == m) >= 2}))
            for _, fn in rng.sample([p for p in pick if p[0] == m], 2):
                next(f for f in mods[m].funcs if f.name == fn).value = counter + len(edited)
                edited.add((m, fn))
        elif kind == "docstring":
            m, fn = rng.choice(pick)
            next(f for f in mods[m].funcs if f.name == fn).doc = f"Value of {m}.{fn} (revision {i})."
            edited.add((m, fn))
        elif kind == "add":
            m = rng.choice(sorted(mods))
            mods[m].funcs.append(Func(f"extra{i}", f"Added in commit {i}.", counter))
        elif kind == "module-comment":
            m = rng.choice(sorted(mods))
            mods[m].comment = f"edited in commit {i}"
        elif kind == "whitespace":
            m, fn = rng.choice(pick)
            next(f for f in mods[m].funcs if f.name == fn).trailing = True
        elif kind == "reorder":
            m = rng.choice(sorted({m for m, _ in pick if sum(1 for x, _ in pick if x == m) >= 2}))
            fs = mods[m].funcs
            a, b = rng.sample(range(len(fs)), 2)
            fs[a], fs[b] = fs[b], fs[a]
        elif kind == "delete":
            m, fn = rng.choice(pick)
            mods[m].funcs = [f for f in mods[m].funcs if f.name != fn]
            alive.discard((m, fn))
            edited.add((m, fn))
        touched = sorted(
            {m for m, mod in mods.items() if (root / f"{m}.py").read_text(encoding="utf-8") != mod.render()}
        )
        write(*touched)
        out.append(Commit(_commit(root, f"{i}: {kind}", i), kind, edited))
    # independent ground truth from the text of every commit
    originals = {(m, fn) for m, fn, _ in facts}
    shas = [initial, *[c.sha for c in out]]
    for before, after, c in zip(shas[:-1], shas[1:], out, strict=True):
        for m in mods:
            old = segments(_git(root, "show", f"{before}:{m}.py"))
            new = segments(_git(root, "show", f"{after}:{m}.py"))
            for fn in set(old) | set(new):
                if (m, fn) in originals and old.get(fn) != new.get(fn):
                    c.truth.add((m, fn))
        if c.truth != c.edited:
            raise AssertionError(
                f"commit {c.kind}: script edits {sorted(c.edited)} != ast truth {sorted(c.truth)}"
            )
    return Repo(root, mods, initial, out, facts)


# ------------------------------------------------------------------------------------------------ the arms
@dataclass
class ArmResult:
    arm: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    truth_total: int = 0
    unflagged_returned: int = 0  # recalled without verify_state suspect although the code changed
    not_returned: int = 0  # not in the top 3 of the recall at all
    flagged_by_kind: dict[str, int] = field(default_factory=dict)
    per_commit: list[dict[str, Any]] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    def to_json(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": self.precision,
            "recall": self.recall,
            "truth_facts_total": self.truth_total,
            "stale_returned_unflagged": self.unflagged_returned,
            "stale_not_returned_in_top3": self.not_returned,
            "flagged_by_kind": self.flagged_by_kind,
            "per_commit": self.per_commit,
        }


def run_arm(
    arm: str, repo: Repo, client: GraphClient, embedder: Embedder, tenant: str | None = None
) -> ArmResult:
    """Play the repository's commits into a fresh tenant graph for one arm and measure it."""
    tenant = tenant or f"l5s_{arm.lower()}_{uuid.uuid4().hex[:8]}"
    graph = graph_name(tenant)
    apply_schema(client, graph)
    eng = Engram(client, graph, embedder)
    stale = Staleness(client, graph, engram=eng)
    try:
        scope = eng.create_scope("global", "global")
        root = toplevel(str(repo.root)) or str(repo.root)
        fids: dict[tuple[str, str], str] = {}
        for m, fn, value in repo.facts:
            fids[(m, fn)] = eng.assert_fact(f"{m}.{fn}", "returns", str(value), scope, "l5")["fact_id"]
        if arm in ("S", "F"):
            text0 = {m: _git(repo.root, "show", f"{repo.initial}:{m}.py") for m in repo.modules}
            symbol_hash = {(m, s.name): s.hash for m, t in text0.items() for s in (python_symbols(t) or [])}
            for (m, fn), fid in fids.items():
                path = absolute_canonical(f"{m}.py", root)
                if arm == "S":
                    stale.anchor_fact(fid, path, fn, symbol_hash[(m, fn)], kind="function")
                else:
                    stale.anchor_fact(fid, path, "", hash_bytes(text0[m].encode()))
        res = ArmResult(arm)
        by_fid = {fid: k for k, fid in fids.items()}
        for c in repo.commits:
            commit, at, groups = commit_groups(str(repo.root), c.sha)
            if arm == "F":
                groups = [g[:1] for g in groups]  # a client that does not parse symbols
            flagged: set[str] = set()
            for chunk in chunk_entries(groups):
                when = at
                for _ in range(20):
                    r = stale.mark_changed(chunk, commit=commit, at=when, agent_id="l5")
                    flagged |= set(r["suspect_fact_ids"])
                    when = r["at"]
                    if not r["truncated"]:
                        break
            got = {by_fid[f] for f in flagged if f in by_fid}
            tp, fp, fn_ = len(got & c.truth), len(got - c.truth), len(c.truth - got)
            res.tp, res.fp, res.fn = res.tp + tp, res.fp + fp, res.fn + fn_
            res.truth_total += len(c.truth)
            res.flagged_by_kind[c.kind] = res.flagged_by_kind.get(c.kind, 0) + len(got)
            unflagged = 0
            for key in sorted(c.truth):
                rows = eng.recall(f"{key[0]}.{key[1]} returns", scope, k=3)
                row = next((x for x in rows if x["fact_id"] == fids[key]), None)
                if row is None:
                    res.not_returned += 1
                elif row["verify_state"] != "suspect":
                    unflagged += 1
            res.unflagged_returned += unflagged
            res.per_commit.append(
                {
                    "commit": c.sha[:10],
                    "kind": c.kind,
                    "truth": len(c.truth),
                    "flagged": len(got),
                    "tp": tp,
                    "fp": fp,
                    "fn": fn_,
                    "unflagged_returned": unflagged,
                }
            )
            for f in sorted(flagged):  # re-confirm so the next commit is measured on its own
                stale.verify_fact(f, True, agent_id="l5", commit=commit)
        return res
    finally:
        client.delete_graph(graph)


def run_staleness(
    client: GraphClient,
    embedder: Embedder,
    workdir: Path,
    modules: int = 12,
    funcs: int = 5,
    commits: int = 20,
) -> dict[str, Any]:
    repo = build_repo(workdir / "repo", modules, funcs, commits)
    arms = {a: run_arm(a, repo, client, embedder) for a in ARMS}
    return {
        "repo": {
            "modules": modules,
            "functions": modules * funcs,
            "change_commits": commits,
            "kinds": [c.kind for c in repo.commits],
            "truth_facts_total": sum(len(c.truth) for c in repo.commits),
            "seed": SEED,
        },
        "arms": {a: r.to_json() for a, r in arms.items()},
    }
