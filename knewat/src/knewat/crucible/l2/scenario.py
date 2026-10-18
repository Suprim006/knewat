"""Play the P3 "Acme Notes API" scenario through any :class:`CoordinationBackend` and keep a ground-truth ledger.

The turn order, the facts, decisions, handoffs, artifacts and episodes are the ones of ``knewat.demo.scripted`` (the
P3 scripted agents), replayed one level below MCP: straight on the backend protocol, so B0 (files), B1 (SQLite),
B2 (vector) and P (Knewat) all end up holding the same story. ``tests/crucible/l2/test_scenario.py`` pins the turn
order against the recording ``demo_data/recordings/acme-scripted/meta.json`` and the texts against ``scripted.py``.

Three things differ from the recorded P3 run, all deliberate and all listed in ``docs``/the results notes:

* the optional *poison* fault is switched on (an unverified forum post asserts ``database=MongoDB 4``, a decision
  is taken on it, then its source is forgotten), because Layer 2 needs a forgetting family;
* ``forget_source`` replaces ``quarantine_source`` (the backend protocol has no quarantine);
* a small **L2 extension** adds one builder decision (``t06``) and two project-scoped facts, so that there are six
  decisions and a scope-isolation question (BASELINE §2 lists six decisions and the memory-scope family).

Everything the questions need is recorded here *while the script runs* (the script knows what it did); no answer is
read back from a backend. Time is an injected clock (``T0 + 1000 ms`` per action) so that every arm gets the same
timestamps in ``assert_fact`` / ``claim_next_task`` and the time-travel questions can name exact instants.
"""

from __future__ import annotations

import contextlib
import importlib
import re
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any

from knewat.crucible.api import CoordinationBackend
from knewat.demo.scenario import OPEN_LEASE_MS, Scenario, load_scenario

T0 = 1_760_000_000_000  # 2025-10-09T08:53:20Z; far in the past so real-clock writes (forget) are always later
TICK = 1000
BUILDER_LEASE_MS = 3000
ROLES = {"planner": "planner", "researcher": "researcher", "builder": "builder"}
BILLING_SCOPE = "project:billing"
ACME_SCOPE = "project:acme"
BILLING_SUBJECT = "Bolt Billing API"

_WORD = re.compile(r"[a-z0-9]+")


def fact_label(predicate: str, value: str) -> str:
    """The canonical name of a fact in questions and answers: ``predicate=value``."""
    return f"{predicate}={' '.join(value.split())}"


def decision_label(text: str) -> str:
    """A decision is named by the first four words of its text (lower case, punctuation dropped)."""
    return " ".join(_WORD.findall(text.casefold())[:4])


class Clock:
    def __init__(self, t0: int = T0):
        self.t = t0

    def tick(self, n: int = 1) -> int:
        self.t += TICK * n
        return self.t


_PATCHED_MODULES = (
    "knewat.crucible.util",
    "knewat.crucible.backends.files",
    "knewat.crucible.backends.sqlite",
    "knewat.crucible.backends.vector",
)


@contextlib.contextmanager
def deterministic(clock: Clock) -> Iterator[None]:
    """Make the file/SQLite/vector arms reproducible while the script plays.

    Their ids come from ``uuid4`` and their log/row timestamps from the wall clock, so two plays of the same script
    would give different bytes and an LLM answer cache keyed on the context could never hit. Inside this block
    ``new_id`` yields a fixed sequence of UUIDs and ``now_ms`` follows the script clock (``clock.t`` plus a counter
    that restarts at every tick), so the same script always writes the same artifacts. The patch is local to the
    backend modules' names; no backend file is edited. The Knewat arm keeps its own ids (nothing LLM-facing reads it).
    """
    counter = {"id": 0, "ms": 0, "last": None}

    def new_id() -> str:
        counter["id"] += 1
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"knewat-crucible-l2/{counter['id']}"))

    def now_ms() -> int:
        if counter["last"] != clock.t:
            counter["last"], counter["ms"] = clock.t, 0
        counter["ms"] += 1
        return clock.t + counter["ms"]

    saved: list[tuple[Any, str, Any]] = []
    mods = [
        importlib.import_module(name) for name in _PATCHED_MODULES
    ]  # import first: a late import would bind the fakes
    for mod in mods:
        for attr, fn in (("new_id", new_id), ("now_ms", now_ms)):
            if hasattr(mod, attr):
                saved.append((mod, attr, getattr(mod, attr)))
                setattr(mod, attr, fn)
    try:
        yield
    finally:
        for mod, attr, old in reversed(saved):
            setattr(mod, attr, old)


@dataclass
class Ledger:
    """What the script did. Plain data, JSON-serialisable (ids are the ones of the arm that was played)."""

    subject: str = ""
    arm: str = ""
    agents: list[str] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)  # {id, title, priority, depends_on, created_at}
    sources: list[dict[str, Any]] = field(default_factory=list)  # {uri, kind, trust, id, added_by, t}
    facts: list[dict[str, Any]] = field(default_factory=list)  # see _Run.assert_
    decisions: list[dict[str, Any]] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    episodes: list[dict[str, Any]] = field(default_factory=list)
    claims: list[dict[str, Any]] = field(
        default_factory=list
    )  # {task_id, agent, reclaimed_from, t, lease_until}
    completions: list[dict[str, Any]] = field(default_factory=list)  # {task_id, agent, artifacts: [uri], t}
    artifacts: list[dict[str, Any]] = field(default_factory=list)  # {id, uri, task_id, agent}
    forgotten: list[dict[str, Any]] = field(default_factory=list)  # {source_uri, fact_labels, t_real}
    events: list[dict[str, Any]] = field(default_factory=list)
    marks: dict[str, int] = field(
        default_factory=dict
    )  # named instants (epoch ms) the time-travel questions use
    turns: list[dict[str, str]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    # -- lookups used by the question builders ------------------------------------------------------------------
    def fact(self, label: str, scope: str | None = None) -> dict[str, Any]:
        hits = [f for f in self.facts if f["label"] == label and (scope is None or f["scope"] == scope)]
        if len(hits) != 1:
            raise KeyError(f"{len(hits)} facts labelled {label!r}")
        return hits[0]

    def decision(self, label: str) -> dict[str, Any]:
        hits = [d for d in self.decisions if d["label"] == label]
        if len(hits) != 1:
            raise KeyError(f"{len(hits)} decisions labelled {label!r}")
        return hits[0]

    def handoff(self, task_id: str) -> dict[str, Any]:
        hits = [h for h in self.handoffs if h["task_id"] == task_id]
        if len(hits) != 1:
            raise KeyError(f"{len(hits)} handoffs for {task_id!r}")
        return hits[0]


# (kind, agent, name, reclaim_from): the P3 turn order (recording acme-scripted), poison turns inserted after t05
TURNS: tuple[tuple[str, str, str, str], ...] = (
    ("init", "planner", "init", ""),
    ("task", "researcher", "t01-gather-requirements", ""),
    ("task", "planner", "t02-choose-api-version", ""),
    ("task", "builder", "t03-design-endpoints", ""),  # the builder dies here
    ("task", "researcher", "t03-design-endpoints", "builder"),  # ... and the researcher takes over
    ("special", "researcher", "ingest-v2", ""),
    ("special", "planner", "adopt-v2", ""),
    ("task", "builder", "t12-update-endpoints-for-v2", ""),
    ("task", "researcher", "t04-survey-infra-security", ""),
    ("task", "planner", "t05-choose-auth", ""),
    ("special", "planner", "ingest-forum-post", ""),  # P3 poison fault (switched on for L2)
    ("special", "researcher", "forget-forum-post", ""),  # forget_source instead of quarantine
    ("special", "researcher", "ext-project-facts", ""),  # L2 extension: project-scoped facts
    ("task", "builder", "t06-write-db-schema", ""),
    ("task", "builder", "t07-implement-crud-spec", ""),
    ("task", "researcher", "t08-write-test-plan", ""),
    ("task", "planner", "t09-review-spec", ""),
    ("task", "researcher", "t10-write-docs", ""),
    ("task", "builder", "t11-package-release", ""),
)


class _Run:
    def __init__(self, b: CoordinationBackend, sc: Scenario, arm: str):
        self.b, self.sc, self.clock = b, sc, Clock()
        self.led = Ledger(subject=sc.subject, arm=arm)
        self.src: dict[str, str] = {}  # source stem -> source id
        self.fid: dict[str, str] = {}  # logical key -> current fact id
        self.art: dict[str, str] = {}  # task id -> artifact id
        self.label_of: dict[str, str] = {}  # fact id -> label
        self.claimed: dict[str, dict[str, Any]] = {}  # agent -> claimed task dict

    # -- primitives ------------------------------------------------------------------------------------------
    def source(self, agent: str, stem: str) -> str:
        d = self.sc.sources[stem]
        sid = self.b.add_source(d.uri, d.kind, d.trust)
        self.src[stem] = sid
        if not any(s["uri"] == d.uri for s in self.led.sources):
            self.led.sources.append(
                {
                    "uri": d.uri,
                    "kind": d.kind,
                    "trust": d.trust,
                    "id": sid,
                    "added_by": agent,
                    "t": self.clock.t,
                }
            )
        return sid

    def assert_(
        self, agent: str, key: str, predicate: str, value: str, stem: str | None, *, subject: str | None = None,
        scope: str = "global", source_uri: str | None = None, source_id: str | None = None,
    ) -> dict[str, Any]:  # fmt: skip
        t = self.clock.tick()
        subj = subject or self.sc.subject
        sid = source_id if source_id is not None else (self.src[stem] if stem else None)
        r = self.b.assert_fact(agent, subj, predicate, value, scope=scope, source_id=sid, now=t)
        self.fid[key] = r["fact_id"]
        label = fact_label(predicate, value)
        self.label_of[r["fact_id"]] = label
        self.led.facts.append(
            {
                "key": key,
                "id": r["fact_id"],
                "label": label,
                "subject": subj,
                "predicate": predicate,
                "value": " ".join(value.split()),
                "scope": scope,
                "agent": agent,
                "source_uri": source_uri or (self.sc.sources[stem].uri if stem else ""),
                "t": t,
                "superseded": [self.label_of[x] for x in r["superseded"]],
                "contradicts": [self.label_of[x] for x in r["contradicts"]],
            }
        )
        return r

    def claim(self, agent: str, expect: str, lease_ms: int, now: int | None = None) -> dict[str, Any]:
        t = now if now is not None else self.clock.tick()
        got = self.b.claim_next_task(agent, lease_ms, now=t)
        if got is None or got["id"] != expect:
            raise RuntimeError(f"{agent} expected to claim {expect}, got {got and got['id']}")
        self.claimed[agent] = got
        self.led.claims.append(
            {
                "task_id": expect,
                "agent": agent,
                "reclaimed_from": got.get("reclaimed_from") or "",
                "t": t,
                "lease_until": got["lease_until"],
            }
        )
        return got

    def finish(self, agent: str, uri: str, summary: str) -> str:
        t = self.claimed[agent]
        r = self.b.complete_task(
            agent, t["id"], t["version"], [{"kind": "file", "uri": uri, "summary": summary}]
        )
        aid = r["artifact_ids"][0]
        self.art[t["id"]] = aid
        self.led.artifacts.append({"id": aid, "uri": uri, "task_id": t["id"], "agent": agent})
        self.led.completions.append(
            {"task_id": t["id"], "agent": agent, "artifacts": [uri], "t": self.clock.tick()}
        )
        return aid

    def complete(self, agent: str) -> None:
        t = self.claimed[agent]
        self.b.complete_task(agent, t["id"], t["version"])
        self.led.completions.append(
            {"task_id": t["id"], "agent": agent, "artifacts": [], "t": self.clock.tick()}
        )

    def decide(self, agent: str, task_id: str, text: str, keys: list[str]) -> str:
        ids = [self.fid[k] for k in keys]
        did = self.b.record_decision(agent, task_id, text, ids)
        self.led.decisions.append(
            {
                "id": did,
                "label": decision_label(text),
                "text": text,
                "task_id": task_id,
                "agent": agent,
                "fact_labels": [self.label_of[i] for i in ids],
                "t": self.clock.tick(),
            }
        )
        return did

    def hand(self, agent: str, to: str, task_id: str, note: str, arts: list[str], keys: list[str]) -> None:
        ids = [self.fid[k] for k in keys]
        self.b.handoff(agent, to, task_id, note, arts, ids)
        uris = {a["id"]: a["uri"] for a in self.led.artifacts}
        self.led.handoffs.append(
            {
                "from": agent,
                "to": to,
                "task_id": task_id,
                "note": note,
                "artifacts": [uris[a] for a in arts],
                "fact_labels": [self.label_of[i] for i in ids],
                "t": self.clock.tick(),
            }
        )

    def episode(self, agent: str, text: str) -> None:
        self.b.remember_episode(agent, text)
        self.led.episodes.append({"agent": agent, "text": text, "t": self.clock.tick()})

    def recall(self, agent: str, query: str) -> None:
        self.b.recall(agent, query, k=5)
        self.clock.tick()

    def event(self, name: str, **info: Any) -> None:
        self.led.events.append({"event": name, "t": self.clock.t, **info})


# ------------------------------------------------------------------------------------------------ task handlers
def _t01(r: _Run, a: str, t: dict) -> None:
    r.source(a, "01_product_brief")
    r.source(a, "02_api_style_guide_v1")
    r.assert_(a, "purpose", "purpose", "REST service to create, tag and search notes", "01_product_brief")
    r.assert_(a, "api_version", "api_version", "v1", "02_api_style_guide_v1")
    r.led.marks["after_v1"] = r.clock.t + TICK // 2  # between v1 and anything later
    r.finish(a, "artifacts/requirements.md", "Requirements: notes CRUD, tags, API version v1")


def _t02(r: _Run, a: str, t: dict) -> None:
    r.decide(
        a,
        t["id"],
        "Build the Acme Notes API against v1 of the style guide (routes under /v1/).",
        ["api_version"],
    )
    r.complete(a)


def _t03(r: _Run, a: str, t: dict, reclaim_from: str) -> None:
    r.recall(a, "API version")
    if reclaim_from:
        text = (
            f"Took over {t['id']} from {reclaim_from}: its lease expired before it finished. "
            "Restarting the endpoint design from the recorded API version."
        )
    else:
        text = "Drafting the endpoint list: list/create/read/update/delete notes under /v1/notes."
    r.episode(a, text)
    art = r.finish(a, "artifacts/openapi-draft.yaml", "Endpoint draft for /v1/notes (CRUD)")
    note = "Endpoint draft is ready." + (
        " Finished on the builder's behalf after it went down." if reclaim_from else ""
    )
    r.hand(a, "builder" if a != "builder" else "planner", t["id"], note, [art], ["api_version"])


def _t04(r: _Run, a: str, t: dict) -> None:
    r.source(a, "03_infra_note")
    r.source(a, "04_security_note")
    r.assert_(a, "database", "database", "PostgreSQL 16", "03_infra_note")
    r.assert_(a, "auth_jwt", "auth_method", "JWT bearer tokens (RS256)", "04_security_note")
    r.led.marks["after_jwt"] = r.clock.t + TICK // 2
    r.finish(a, "artifacts/constraints.md", "Infra and security constraints: PostgreSQL 16, JWT auth")


def _t05(r: _Run, a: str, t: dict) -> None:
    r.recall(a, "authentication")
    r.source(a, "05_customer_request")
    res = r.assert_(a, "auth_apikey", "auth_method", "API key in X-Api-Key header", "05_customer_request")
    r.event(
        "auth_contradiction",
        agent=a,
        new_fact=r.label_of[res["fact_id"]],
        contradicts=[r.label_of[x] for x in res["contradicts"]],
    )
    r.led.marks["after_apikey"] = r.clock.t + TICK // 2
    r.decide(
        a,
        t["id"],
        "Use JWT bearer tokens for user traffic (security requirement); offer API keys only later for service accounts.",
        ["auth_jwt", "auth_apikey"],
    )
    r.complete(a)


def _t06(r: _Run, a: str, t: dict) -> None:
    r.recall(a, "database")
    r.episode(a, "Schema: notes, tags and note_tags tables in PostgreSQL 16.")
    # L2 extension: the one decision the P3 script does not take
    r.decide(
        a,
        t["id"],
        "Use PostgreSQL 16 for the notes, tags and note_tags tables.",
        ["database"],
    )
    r.finish(a, "artifacts/schema.sql", "PostgreSQL 16 schema: notes, tags, note_tags")


def _t07(r: _Run, a: str, t: dict) -> None:
    r.recall(a, "API version")
    r.recall(a, "authentication")
    art = r.finish(a, "artifacts/crud-spec.md", "CRUD spec for the current API version with JWT auth")
    r.hand(a, "planner", t["id"], "CRUD spec ready for review.", [art], ["api_version", "auth_jwt"])


def _t08(r: _Run, a: str, t: dict) -> None:
    r.recall(a, "API version")
    r.finish(a, "artifacts/test-plan.md", "Test plan for the CRUD endpoints")


def _t09(r: _Run, a: str, t: dict) -> None:
    r.recall(a, "API version")
    r.decide(
        a,
        t["id"],
        "Spec approved: endpoints, schema and JWT auth are consistent.",
        ["api_version", "auth_jwt"],
    )
    r.complete(a)


def _t10(r: _Run, a: str, t: dict) -> None:
    r.recall(a, "API version")
    r.finish(a, "artifacts/docs.md", "API documentation")


def _t11(r: _Run, a: str, t: dict) -> None:
    art = r.finish(a, "artifacts/release.tar", "Release bundle of the Acme Notes API")
    r.hand(a, "planner", t["id"], "Release bundle is ready.", [art], ["api_version"])


def _t12(r: _Run, a: str, t: dict) -> None:
    r.recall(a, "API version")
    r.episode(
        a, "Endpoint design moves from /v1/ to /v2/: page_token/page_size lists and problem+json errors."
    )
    art = r.finish(a, "artifacts/openapi-v2.yaml", "Endpoint design for /v2/notes")
    r.hand(a, "planner", t["id"], "Updated for API v2.", [art], ["api_version"])


_TASKS = {
    "t01-gather-requirements": _t01,
    "t02-choose-api-version": _t02,
    "t04-survey-infra-security": _t04,
    "t05-choose-auth": _t05,
    "t06-write-db-schema": _t06,
    "t07-implement-crud-spec": _t07,
    "t08-write-test-plan": _t08,
    "t09-review-spec": _t09,
    "t10-write-docs": _t10,
    "t11-package-release": _t11,
    "t12-update-endpoints-for-v2": _t12,
}


# ------------------------------------------------------------------------------------------------ special turns
def _ingest_v2(r: _Run, a: str) -> None:
    r.led.marks["before_v2"] = r.clock.t + TICK // 2
    r.source(a, "06_api_style_guide_v2")
    res = r.assert_(a, "api_version", "api_version", "v2", "06_api_style_guide_v2")
    r.event(
        "version_superseded",
        agent=a,
        new_fact="api_version=v2",
        superseded=[r.label_of[x] for x in res["superseded"]],
    )
    r.led.marks["after_v2"] = r.clock.t + TICK // 2
    r.episode(a, "Style guide v2 was published: API version v1 is withdrawn, routes move to /v2/.")


def _adopt_v2(r: _Run, a: str) -> None:
    r.recall(a, "API version")
    r.decide(
        a,
        "t02-choose-api-version",
        "Adopt style guide v2: the API version is now v2 (routes under /v2/).",
        ["api_version"],
    )
    r.b.create_tasks([r.sc.task("t12-update-endpoints-for-v2").spec()])
    t12 = r.sc.task("t12-update-endpoints-for-v2")
    r.led.tasks.append(
        {"id": t12.id, "title": t12.title, "priority": t12.priority, "depends_on": list(t12.depends_on)}
    )
    r.event("task_created_for_v2", task="t12-update-endpoints-for-v2")


def _ingest_forum_post(r: _Run, a: str) -> None:
    r.source(a, "07_forum_post_unverified")
    res = r.assert_(a, "database_poison", "database", "MongoDB 4", "07_forum_post_unverified")
    r.event(
        "poison_fact",
        agent=a,
        fact="database=MongoDB 4",
        contradicts=[r.label_of[x] for x in res["contradicts"]],
    )
    r.decide(
        a, "t06-write-db-schema", "Evaluate MongoDB 4 as the database (forum post).", ["database_poison"]
    )


def _forget_forum_post(r: _Run, a: str) -> None:
    r.recall(a, "database")
    sid = r.source(a, "07_forum_post_unverified")
    res = r.b.forget_source(sid)
    uri = r.sc.sources["07_forum_post_unverified"].uri
    r.led.forgotten.append(
        {"source_uri": uri, "fact_labels": [r.label_of[i] for i in res["fact_ids"]], "t": r.clock.tick()}
    )
    r.event("forget_source", source=uri, facts=[r.label_of[i] for i in res["fact_ids"]])


def _ext_project_facts(r: _Run, a: str) -> None:
    """L2 extension (not in P3): one fact per project scope, for the scope-isolation questions."""
    sid = r.b.add_source("billing-docs/01_overview.md", "doc", 1.0)
    r.led.sources.append(
        {"uri": "billing-docs/01_overview.md", "kind": "doc", "trust": 1.0, "id": sid, "added_by": a, "t": r.clock.t}
    )  # fmt: skip
    r.assert_(
        a, "billing_cycle", "billing_cycle", "monthly", None, subject=BILLING_SUBJECT, scope=BILLING_SCOPE,
        source_uri="billing-docs/01_overview.md", source_id=sid,
    )  # fmt: skip
    r.assert_(
        "planner", "release_channel", "release_channel", "closed beta", None, scope=ACME_SCOPE,
    )  # fmt: skip


_SPECIALS = {
    "ingest-v2": _ingest_v2,
    "adopt-v2": _adopt_v2,
    "ingest-forum-post": _ingest_forum_post,
    "forget-forum-post": _forget_forum_post,
    "ext-project-facts": _ext_project_facts,
}


def play(backend: CoordinationBackend, scenario: Scenario | None = None) -> Ledger:
    """Run the scenario on ``backend`` (an empty tenant) and return the ground-truth ledger."""
    sc = scenario or load_scenario()
    r = _Run(backend, sc, getattr(backend, "name", ""))
    led = r.led
    with deterministic(r.clock):
        for agent, role in ROLES.items():
            backend.register_agent(agent, role)
        led.agents = list(ROLES)
        for kind, agent, name, reclaim_from in TURNS:
            led.turns.append({"kind": kind, "agent": agent, "name": name, "reclaim_from": reclaim_from})
            if kind == "init":
                backend.create_tasks([t.spec() for t in sc.tasks])
                led.tasks += [
                    {"id": t.id, "title": t.title, "priority": t.priority, "depends_on": list(t.depends_on)}
                    for t in sc.tasks
                ]
            elif kind == "special":
                _SPECIALS[name](r, agent)
            elif name == "t03-design-endpoints" and not reclaim_from:
                # the builder claims t03, makes one call, then dies with its lease left to expire
                got = r.claim(agent, name, BUILDER_LEASE_MS)
                r.recall(agent, "API version")
                r.event("kill_builder", agent=agent, task=name, lease_until=got["lease_until"])
            elif name == "t03-design-endpoints":
                lease_until = led.claims[-1]["lease_until"]
                r.clock.t = lease_until + TICK // 2  # the scheduler waits for the lease to expire
                r.claim(agent, name, OPEN_LEASE_MS, now=r.clock.tick())
                r.event("reclaim", task=name, agent=agent, reclaimed_from=reclaim_from)
                _t03(r, agent, {"id": name, "version": r.claimed[agent]["version"]}, reclaim_from)
            else:
                t = r.claim(agent, name, OPEN_LEASE_MS)
                _TASKS[name](r, agent, t)
    # the clock reading the questions refer to as "the end"
    led.marks["end"] = r.clock.t + TICK
    return led
