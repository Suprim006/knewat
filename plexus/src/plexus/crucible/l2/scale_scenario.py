"""L2-at-scale scenario: K independent Acme sprints played one after another into ONE tenant per arm.

``scenario.py`` plays one Acme project (12 tasks, 6 decisions, 4 handoffs, a v1 -> v2 supersede, an auth conflict, a
killed builder, a poisoned and forgotten source). Here the same story is repeated for ``K`` sprints (``S01`` ... ``Sxx``)
so that the team's whole history is far larger than the 32k-character context budget. Each sprint is an independent
project with its own tasks, sources, facts, decisions, handoffs and episodes:

* ids, uris, subjects, scopes and decision texts carry the sprint tag (``s07-t03-design-endpoints``,
  ``acme-docs/s07/02_api_style_guide_v1.md``, subject ``Acme Notes API S07``, scope ``project:acme-s07``, decision
  ``S07: Use JWT bearer tokens ...``), so a sprint's records can be found by keyword and never collide with another's;
* the values vary per sprint (API versions ``v13 -> v14`` in S07, the database, the JWT key, the API-key header, the
  poisoned database, the release channel, the billing cycle), so sprints are distinguishable and labels are unique;
* the turn order, the fault script and the texts are those of ``scenario.py`` (the P3 script + the L2 additions);
  ``tests/crucible/l2/test_scale_scenario.py`` pins the turn order against ``scenario.TURNS``.

All sprints share one deterministic clock and one deterministic id sequence (``scenario.deterministic``), so the file,
SQLite and vector arms are byte-reproducible and the LLM answer cache can hit. Ground truth is the per-sprint
:class:`~plexus.crucible.l2.scenario.Ledger` the script keeps while it runs.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from plexus.crucible.api import CoordinationBackend
from plexus.crucible.l2.scenario import (
    BUILDER_LEASE_MS,
    ROLES,
    TICK,
    TURNS,
    Clock,
    Ledger,
    _Run,
    deterministic,
)
from plexus.demo.scenario import OPEN_LEASE_MS, Scenario, load_scenario

DATABASES = (
    "PostgreSQL 16", "MySQL 8", "MariaDB 11", "CockroachDB 24", "SQL Server 2022", "Oracle 23",
    "PostgreSQL 15", "Db2 12", "TiDB 8", "Aurora MySQL 3",
)  # fmt: skip
POISONS = ("MongoDB", "Cassandra", "Couchbase", "DynamoDB", "Redis", "CouchDB", "RethinkDB", "Neo4j", "ScyllaDB", "Riak")
JWT_ALGS = ("RS256", "ES256", "PS256", "RS384", "ES384")
KEY_HEADERS = (
    "Api-Key", "Service-Key", "Client-Key", "Auth-Key", "App-Key", "Access-Key", "Team-Key", "Notes-Key",
    "Gateway-Key", "Partner-Key", "Tenant-Key", "Edge-Key", "Core-Key", "Mobile-Key", "Web-Key", "Batch-Key",
    "Hook-Key", "Sync-Key", "Cloud-Key", "Ops-Key",
)  # fmt: skip
CHANNELS = ("closed beta", "open beta", "private preview", "early access", "general availability")
CYCLES = ("monthly", "weekly", "quarterly", "biweekly")
MAX_SPRINTS = len(KEY_HEADERS)  # the API-key header must be unique per sprint (it labels a fact that questions look up)


@dataclass(frozen=True)
class Sprint:
    n: int  # 1-based

    @property
    def tag(self) -> str:
        return f"S{self.n:02d}"

    @property
    def low(self) -> str:
        return self.tag.lower()

    @property
    def p(self) -> str:  # task id prefix
        return f"{self.low}-"

    @property
    def subject(self) -> str:
        return f"Acme Notes API {self.tag}"

    @property
    def v_old(self) -> str:
        return f"v{2 * self.n - 1}"

    @property
    def v_new(self) -> str:
        return f"v{2 * self.n}"

    @property
    def db(self) -> str:
        return DATABASES[(self.n - 1) % len(DATABASES)]

    @property
    def poison(self) -> str:
        return f"{POISONS[(self.n - 1) % len(POISONS)]} {self.n + 3}"

    @property
    def jwt(self) -> str:
        return f"JWT bearer tokens ({JWT_ALGS[(self.n - 1) % len(JWT_ALGS)]}, key {self.low})"

    @property
    def apikey(self) -> str:
        return f"API key in X-{KEY_HEADERS[self.n - 1]} header"

    @property
    def channel(self) -> str:
        return CHANNELS[(self.n - 1) % len(CHANNELS)]

    @property
    def cycle(self) -> str:
        return f"{CYCLES[(self.n - 1) % len(CYCLES)]}, invoiced on day {self.n}"

    @property
    def billing_subject(self) -> str:
        return f"Bolt Billing API {self.tag}"

    @property
    def acme_scope(self) -> str:
        return f"project:acme-{self.low}"

    @property
    def billing_scope(self) -> str:
        return f"project:billing-{self.low}"

    @property
    def billing_uri(self) -> str:
        return f"billing-docs/{self.low}/01_overview.md"

    def art(self, name: str) -> str:
        return f"artifacts/{self.low}/{name}"

    def tid(self, name: str) -> str:
        return self.p + name

    # decision texts (their first four words name them: the tag keeps them unique across sprints)
    @property
    def d_build(self) -> str:
        return f"{self.tag}: Build the Acme Notes API against {self.v_old} of the style guide (routes under /{self.v_old}/)."

    @property
    def d_adopt(self) -> str:
        return f"{self.tag}: Adopt style guide {self.v_new}: the API version is now {self.v_new} (routes under /{self.v_new}/)."

    @property
    def d_jwt(self) -> str:
        return f"{self.tag}: Use JWT bearer tokens for user traffic (security requirement); offer API keys only later for service accounts."

    @property
    def d_ok(self) -> str:
        return f"{self.tag}: Spec approved: endpoints, schema and JWT auth are consistent."

    @property
    def d_poison(self) -> str:
        return f"{self.tag}: Evaluate {self.poison} as the database (forum post)."

    @property
    def d_db(self) -> str:
        return f"{self.tag}: Use {self.db} for the notes, tags and note_tags tables."


def sprint_scenario(base: Scenario, sp: Sprint) -> Scenario:
    """The base Acme scenario with this sprint's task ids, source uris and subject."""

    def task(t: Any) -> Any:
        return dataclasses.replace(
            t,
            id=sp.tid(t.id),
            title=f"{t.title} ({sp.tag})",
            depends_on=tuple(sp.tid(d) for d in t.depends_on),
        )

    def source(s: Any) -> Any:
        head, _, tail = s.uri.partition("/")
        return dataclasses.replace(s, uri=f"{head}/{sp.low}/{tail}")

    return Scenario(
        subject=sp.subject,
        sources={k: source(v) for k, v in base.sources.items()},
        tasks=tuple(task(t) for t in base.tasks),
        extra_tasks=tuple(task(t) for t in base.extra_tasks),
        specials=base.specials,
    )


# ------------------------------------------------------------------------------------------------ handlers
def _recall(r: _Run, a: str, sp: Sprint, q: str) -> None:
    r.recall(a, f"{q} {sp.tag}")


def _t01(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    r.source(a, "01_product_brief")
    r.source(a, "02_api_style_guide_v1")
    r.assert_(a, "purpose", "purpose", f"REST service to create, tag and search notes ({sp.tag})", "01_product_brief")
    r.assert_(a, "api_version", "api_version", sp.v_old, "02_api_style_guide_v1")
    r.led.marks["after_v1"] = r.clock.t + TICK // 2
    r.finish(a, sp.art("requirements.md"), f"{sp.tag} requirements: notes CRUD, tags, API version {sp.v_old}")


def _t02(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    r.decide(a, t["id"], sp.d_build, ["api_version"])
    r.complete(a)


def _t03(r: _Run, sp: Sprint, a: str, t: dict, reclaim_from: str) -> None:
    _recall(r, a, sp, "API version")
    if reclaim_from:
        text = (
            f"{sp.tag}: Took over {t['id']} from {reclaim_from}: its lease expired before it finished. "
            "Restarting the endpoint design from the recorded API version."
        )
    else:
        text = f"{sp.tag}: Drafting the endpoint list: list/create/read/update/delete notes under /{sp.v_old}/notes."
    r.episode(a, text)
    art = r.finish(a, sp.art("openapi-draft.yaml"), f"{sp.tag} endpoint draft for /{sp.v_old}/notes (CRUD)")
    note = f"{sp.tag}: Endpoint draft is ready." + (
        " Finished on the builder's behalf after it went down." if reclaim_from else ""
    )
    r.hand(a, "builder" if a != "builder" else "planner", t["id"], note, [art], ["api_version"])


def _t04(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    r.source(a, "03_infra_note")
    r.source(a, "04_security_note")
    r.assert_(a, "database", "database", sp.db, "03_infra_note")
    r.assert_(a, "auth_jwt", "auth_method", sp.jwt, "04_security_note")
    r.led.marks["after_jwt"] = r.clock.t + TICK // 2
    r.finish(a, sp.art("constraints.md"), f"{sp.tag} infra and security constraints: {sp.db}, JWT auth")


def _t05(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    _recall(r, a, sp, "authentication")
    r.source(a, "05_customer_request")
    res = r.assert_(a, "auth_apikey", "auth_method", sp.apikey, "05_customer_request")
    r.event(
        "auth_contradiction",
        agent=a,
        new_fact=r.label_of[res["fact_id"]],
        contradicts=[r.label_of[x] for x in res["contradicts"]],
    )
    r.led.marks["after_apikey"] = r.clock.t + TICK // 2
    r.decide(a, t["id"], sp.d_jwt, ["auth_jwt", "auth_apikey"])
    r.complete(a)


def _t06(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    _recall(r, a, sp, "database")
    r.episode(a, f"{sp.tag}: Schema: notes, tags and note_tags tables in {sp.db}.")
    r.decide(a, t["id"], sp.d_db, ["database"])
    r.finish(a, sp.art("schema.sql"), f"{sp.tag} {sp.db} schema: notes, tags, note_tags")


def _t07(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    _recall(r, a, sp, "API version")
    _recall(r, a, sp, "authentication")
    art = r.finish(a, sp.art("crud-spec.md"), f"{sp.tag} CRUD spec for the current API version with JWT auth")
    r.hand(a, "planner", t["id"], f"{sp.tag}: CRUD spec ready for review.", [art], ["api_version", "auth_jwt"])


def _t08(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    _recall(r, a, sp, "API version")
    r.finish(a, sp.art("test-plan.md"), f"{sp.tag} test plan for the CRUD endpoints")


def _t09(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    _recall(r, a, sp, "API version")
    r.decide(a, t["id"], sp.d_ok, ["api_version", "auth_jwt"])
    r.complete(a)


def _t10(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    _recall(r, a, sp, "API version")
    r.finish(a, sp.art("docs.md"), f"{sp.tag} API documentation")


def _t11(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    art = r.finish(a, sp.art("release.tar"), f"{sp.tag} release bundle of the Acme Notes API")
    r.hand(a, "planner", t["id"], f"{sp.tag}: Release bundle is ready.", [art], ["api_version"])


def _t12(r: _Run, sp: Sprint, a: str, t: dict) -> None:
    _recall(r, a, sp, "API version")
    r.episode(
        a,
        f"{sp.tag}: Endpoint design moves from /{sp.v_old}/ to /{sp.v_new}/: page_token/page_size lists and problem+json errors.",
    )
    art = r.finish(a, sp.art("openapi-v2.yaml"), f"{sp.tag} endpoint design for /{sp.v_new}/notes")
    r.hand(a, "planner", t["id"], f"{sp.tag}: Updated for API {sp.v_new}.", [art], ["api_version"])


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


def _ingest_v2(r: _Run, sp: Sprint, a: str) -> None:
    r.led.marks["before_v2"] = r.clock.t + TICK // 2
    r.source(a, "06_api_style_guide_v2")
    res = r.assert_(a, "api_version", "api_version", sp.v_new, "06_api_style_guide_v2")
    r.event(
        "version_superseded",
        agent=a,
        new_fact=f"api_version={sp.v_new}",
        superseded=[r.label_of[x] for x in res["superseded"]],
    )
    r.led.marks["after_v2"] = r.clock.t + TICK // 2
    r.episode(a, f"{sp.tag}: Style guide {sp.v_new} was published: API version {sp.v_old} is withdrawn, routes move to /{sp.v_new}/.")


def _adopt_v2(r: _Run, sp: Sprint, a: str) -> None:
    _recall(r, a, sp, "API version")
    r.decide(a, sp.tid("t02-choose-api-version"), sp.d_adopt, ["api_version"])
    t12 = r.sc.task(sp.tid("t12-update-endpoints-for-v2"))
    r.b.create_tasks([t12.spec()])
    r.led.tasks.append(
        {"id": t12.id, "title": t12.title, "priority": t12.priority, "depends_on": list(t12.depends_on)}
    )
    r.event("task_created_for_v2", task=t12.id)


def _ingest_forum_post(r: _Run, sp: Sprint, a: str) -> None:
    r.source(a, "07_forum_post_unverified")
    res = r.assert_(a, "database_poison", "database", sp.poison, "07_forum_post_unverified")
    r.event(
        "poison_fact", agent=a, fact=f"database={sp.poison}", contradicts=[r.label_of[x] for x in res["contradicts"]]
    )
    r.decide(a, sp.tid("t06-write-db-schema"), sp.d_poison, ["database_poison"])


def _forget_forum_post(r: _Run, sp: Sprint, a: str) -> None:
    _recall(r, a, sp, "database")
    sid = r.source(a, "07_forum_post_unverified")
    res = r.b.forget_source(sid)
    uri = r.sc.sources["07_forum_post_unverified"].uri
    r.led.forgotten.append(
        {"source_uri": uri, "fact_labels": [r.label_of[i] for i in res["fact_ids"]], "t": r.clock.tick()}
    )
    r.event("forget_source", source=uri, facts=[r.label_of[i] for i in res["fact_ids"]])


def _ext_project_facts(r: _Run, sp: Sprint, a: str) -> None:
    sid = r.b.add_source(sp.billing_uri, "doc", 1.0)
    r.led.sources.append(
        {"uri": sp.billing_uri, "kind": "doc", "trust": 1.0, "id": sid, "added_by": a, "t": r.clock.t}
    )  # fmt: skip
    r.assert_(
        a, "billing_cycle", "billing_cycle", sp.cycle, None, subject=sp.billing_subject, scope=sp.billing_scope,
        source_uri=sp.billing_uri, source_id=sid,
    )  # fmt: skip
    r.assert_("planner", "release_channel", "release_channel", sp.channel, None, scope=sp.acme_scope)


_SPECIALS = {
    "ingest-v2": _ingest_v2,
    "adopt-v2": _adopt_v2,
    "ingest-forum-post": _ingest_forum_post,
    "forget-forum-post": _forget_forum_post,
    "ext-project-facts": _ext_project_facts,
}


def play_sprint(b: CoordinationBackend, base: Scenario, sp: Sprint, clock: Clock) -> Ledger:
    """One sprint on an already-registered backend. Must run inside ``deterministic(clock)``."""
    sc = sprint_scenario(base, sp)
    r = _Run(b, sc, getattr(b, "name", ""))
    r.clock = clock  # one clock for the whole history
    led = r.led
    led.agents = list(ROLES)
    for kind, agent, name, reclaim_from in TURNS:
        led.turns.append({"kind": kind, "agent": agent, "name": name, "reclaim_from": reclaim_from})
        if kind == "init":
            b.create_tasks([t.spec() for t in sc.tasks])
            led.tasks += [
                {"id": t.id, "title": t.title, "priority": t.priority, "depends_on": list(t.depends_on)}
                for t in sc.tasks
            ]
        elif kind == "special":
            _SPECIALS[name](r, sp, agent)
        elif name == "t03-design-endpoints" and not reclaim_from:
            tid = sp.tid(name)
            got = r.claim(agent, tid, BUILDER_LEASE_MS)
            _recall(r, agent, sp, "API version")
            r.event("kill_builder", agent=agent, task=tid, lease_until=got["lease_until"])
        elif name == "t03-design-endpoints":
            tid = sp.tid(name)
            lease_until = led.claims[-1]["lease_until"]
            r.clock.t = max(r.clock.t, lease_until) + TICK // 2  # the scheduler waits for the lease to expire
            r.claim(agent, tid, OPEN_LEASE_MS, now=r.clock.tick())
            r.event("reclaim", task=tid, agent=agent, reclaimed_from=reclaim_from)
            _t03(r, sp, agent, {"id": tid, "version": r.claimed[agent]["version"]}, reclaim_from)
        else:
            tid = sp.tid(name)
            t = r.claim(agent, tid, OPEN_LEASE_MS)
            _TASKS[name](r, sp, agent, t)
    led.marks["end"] = r.clock.t + TICK
    led.subject = sp.subject
    return led


@dataclass
class ScaleLedger:
    sprints: list[Sprint]
    ledgers: list[Ledger]

    def of(self, n: int) -> tuple[Sprint, Ledger]:
        return self.sprints[n - 1], self.ledgers[n - 1]

    def summary(self) -> dict[str, Any]:
        ls = self.ledgers
        return {
            "sprints": len(ls),
            "agents": ls[0].agents if ls else [],
            "tasks": sum(len(x.tasks) for x in ls),
            "decisions": sum(len(x.decisions) for x in ls),
            "handoffs": sum(len(x.handoffs) for x in ls),
            "facts": sum(len(x.facts) for x in ls),
            "episodes": sum(len(x.episodes) for x in ls),
            "sources": sum(len(x.sources) for x in ls),
            "supersedes": sum(len(f["superseded"]) for x in ls for f in x.facts),
            "conflicting_pairs": sum(1 for x in ls for f in x.facts if f["contradicts"]),
            "reclaims": sum(1 for x in ls for c in x.claims if c["reclaimed_from"]),
            "forgotten_facts": sum(len(g["fact_labels"]) for x in ls for g in x.forgotten),
        }


def play_scale(backend: CoordinationBackend, k: int, scenario: Scenario | None = None) -> ScaleLedger:
    """Play ``k`` sprints into one empty tenant and return the ground truth of every sprint."""
    if not 1 <= k <= MAX_SPRINTS:
        raise ValueError(f"k must be 1..{MAX_SPRINTS}")
    base = scenario or load_scenario()
    clock = Clock()
    sprints = [Sprint(n) for n in range(1, k + 1)]
    ledgers: list[Ledger] = []
    with deterministic(clock):
        for agent, role in ROLES.items():
            backend.register_agent(agent, role)
        for sp in sprints:
            ledgers.append(play_sprint(backend, base, sp, clock))
            clock.tick(5)  # a gap between sprints
    for led in ledgers:
        led.arm = getattr(backend, "name", "")
    return ScaleLedger(sprints, ledgers)
