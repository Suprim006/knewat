"""The "Acme Notes API" demo scenario: synthetic sources, the task DAG and the fault script.

Everything here is data. ``demo_data/acme/`` holds the source documents (``sources/*.md``), the task DAG and the
per-task briefs the real Claude agents get (``tasks.json``), and the role prompts (``roles/*.md``). The scripted
agents (``plexus.demo.scripted``) and the real ``claude -p`` orchestrator (``plexus.demo.orchestrator``) play the
same scenario through the same MCP tools.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

ROLES = ("planner", "researcher", "builder")
OPEN_LEASE_MS = 120_000  # lease for ordinary (non-fault) work: far longer than any scripted turn
RECORDINGS_DIRNAME = "recordings"


def demo_data_dir() -> Path:
    """``plexus/demo_data`` (override with env ``PLEXUS_DEMO_DATA``)."""
    env = os.environ.get("PLEXUS_DEMO_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "demo_data"


def recordings_dir() -> Path:
    return demo_data_dir() / RECORDINGS_DIRNAME


@dataclass(frozen=True)
class SourceDoc:
    stem: str  # file stem, e.g. '02_api_style_guide_v1'
    title: str  # first heading of the document
    uri: str  # stable uri used as the Source key, e.g. 'acme-docs/02_api_style_guide_v1.md'
    kind: str
    trust: float
    text: str


@dataclass(frozen=True)
class TaskDef:
    id: str
    title: str
    role: str
    priority: int
    depends_on: tuple[str, ...]
    sources: tuple[str, ...]
    brief: str

    def spec(self) -> dict[str, Any]:
        """The ``create_tasks`` item for this task."""
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "depends_on": list(self.depends_on),
        }


@dataclass(frozen=True)
class SpecialDef:
    name: str
    role: str
    sources: tuple[str, ...]
    brief: str


@dataclass(frozen=True)
class Scenario:
    subject: str
    sources: dict[str, SourceDoc]
    tasks: tuple[TaskDef, ...]  # created by the planner at the start
    extra_tasks: tuple[TaskDef, ...]  # created mid-run (the v2 reaction)
    specials: dict[str, SpecialDef]

    def task(self, task_id: str) -> TaskDef:
        for t in (*self.tasks, *self.extra_tasks):
            if t.id == task_id:
                return t
        raise KeyError(task_id)

    @property
    def all_tasks(self) -> tuple[TaskDef, ...]:
        return (*self.tasks, *self.extra_tasks)


# the kind / trust of each source document (the uri is derived from the file name)
_SOURCE_META: dict[str, tuple[str, float]] = {
    "05_customer_request": ("chat", 0.8),
    "07_forum_post_unverified": ("web", 0.2),
}


def _source(path: Path) -> SourceDoc:
    text = path.read_text(encoding="utf-8").strip()
    m = re.match(r"#\s*(.+)", text)
    kind, trust = _SOURCE_META.get(path.stem, ("doc", 1.0))
    return SourceDoc(
        path.stem, m.group(1).strip() if m else path.stem, f"acme-docs/{path.name}", kind, trust, text
    )


def _task(d: dict[str, Any]) -> TaskDef:
    return TaskDef(
        id=d["id"],
        title=d["title"],
        role=d["role"],
        priority=int(d["priority"]),
        depends_on=tuple(d["depends_on"]),
        sources=tuple(d.get("sources", ())),
        brief=d["brief"],
    )


@lru_cache(maxsize=4)
def _load(root: str) -> Scenario:
    base = Path(root) / "acme"
    sources = {p.stem: _source(p) for p in sorted((base / "sources").glob("*.md"))}
    raw = json.loads((base / "tasks.json").read_text(encoding="utf-8"))
    specials = {
        name: SpecialDef(name, s["role"], tuple(s.get("sources", ())), s["brief"])
        for name, s in raw["specials"].items()
    }
    sc = Scenario(
        subject=raw["subject"],
        sources=sources,
        tasks=tuple(_task(t) for t in raw["tasks"]),
        extra_tasks=tuple(_task(t) for t in raw["extra_tasks"]),
        specials=specials,
    )
    for t in sc.all_tasks:
        missing = [s for s in t.sources if s not in sources]
        if missing or t.role not in ROLES:
            raise ValueError(f"scenario task {t.id}: unknown source(s) {missing} or role {t.role!r}")
    return sc


def load_scenario(root: Path | None = None) -> Scenario:
    return _load(str(root or demo_data_dir()))


def role_prompt(role: str, root: Path | None = None) -> str:
    return ((root or demo_data_dir()) / "acme" / "roles" / f"{role}.md").read_text(encoding="utf-8")


@dataclass
class FaultScript:
    """What goes wrong, and at which (global) step. Steps count tool calls across all agents.

    * ``kill_builder_at``: from this step on, the first time the builder holds a claimed task and is about to
      make its next call, it dies (its lease is left to expire). The lease is ``builder_lease_ms``; the
      scheduler then waits for it to expire and ``reclaimer`` takes the task over (``reclaimed_from=builder``).
    * ``publish_v2_at``: at the first scheduling point at or after this step the v2 style guide is "published":
      the researcher ingests it (superseding ``api_version`` v1 -> v2) and the planner reacts.
    * ``poison_at`` (stretch, off by default): an unverified forum post arrives with a conflicting database
      claim and is then quarantined.
    * The conflicting auth assertion (JWT vs API key from two agents) is part of task ``t05``, not a timed fault.
    """

    kill_builder_at: int | None = 15
    publish_v2_at: int | None = 20
    poison_at: int | None = None
    builder_lease_ms: int = 3000
    reclaimer: str = "researcher"
    fired: dict[str, int] = field(default_factory=dict)  # fault name -> step it fired at

    def due(self, name: str, at: int | None, step: int) -> bool:
        return at is not None and name not in self.fired and step >= at

    def fire(self, name: str, step: int) -> None:
        self.fired[name] = step
