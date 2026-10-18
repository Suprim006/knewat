"""The shared suite: every arm must satisfy the CoordinationBackend contract (api.py docstring).

Lineage calls may raise ``Unsupported`` only in arms that do not declare the capability.
"""

from __future__ import annotations

import threading
import time

import pytest

from plexus.crucible.api import (
    OPEN,
    BackendSpec,
    ClaimConflict,
    CoordinationBackend,
    InvalidTenant,
    UnknownReference,
    Unsupported,
)
from plexus.crucible.backends import open_backend


def agent(b, name="a1", role=""):
    b.register_agent(name, role)
    return name


# -- protocol ---------------------------------------------------------------------------------------------------


def test_satisfies_protocol(backend):
    assert isinstance(backend, CoordinationBackend)
    assert backend.name and backend.label and isinstance(backend.capabilities, frozenset)


# -- tasks ---------------------------------------------------------------------------------------------------------


def test_claim_order_priority_then_creation(backend):
    a = agent(backend)
    ids = backend.create_tasks(
        [
            {"id": "t-low", "title": "low", "priority": 0},
            {"id": "t-high", "title": "high", "priority": 5},
            {"id": "t-low2", "title": "low2", "priority": 0},
        ]
    )
    assert ids == ["t-low", "t-high", "t-low2"]
    got = [backend.claim_next_task(a, 60_000)["id"] for _ in range(3)]
    assert got == ["t-high", "t-low", "t-low2"]
    assert backend.claim_next_task(a, 60_000) is None


def test_claim_result_shape_and_version(backend):
    a = agent(backend)
    backend.create_tasks([{"id": "t1", "title": "one"}])
    t = backend.claim_next_task(a, 1_000, now=10_000)
    assert t["id"] == "t1" and t["version"] == 1 and t["lease_until"] == 11_000 and t["reclaimed_from"] == ""
    st = backend.task_status("t1")
    assert st["status"] == "claimed" and st["claimed_by"] == a and st["version"] == 1
    assert backend.task_status("nope") is None


def test_dependencies_block_until_done(backend):
    a = agent(backend)
    backend.create_tasks(
        [
            {"id": "root", "title": "root"},
            {"id": "mid", "title": "mid", "depends_on": ["root"]},
            {"id": "leaf", "title": "leaf", "depends_on": ["mid", "root"]},
        ]
    )
    t = backend.claim_next_task(a, 60_000)
    assert t["id"] == "root"
    assert backend.claim_next_task(a, 60_000) is None  # mid waits for root, nothing else is ready
    backend.complete_task(a, "root", t["version"])
    t = backend.claim_next_task(a, 60_000)
    assert t["id"] == "mid"
    assert backend.claim_next_task(a, 60_000) is None
    backend.complete_task(a, "mid", t["version"])
    assert backend.claim_next_task(a, 60_000)["id"] == "leaf"
    deps = {d["id"]: d["status"] for d in backend.task_status("leaf")["dependencies"]}
    assert deps == {"mid": "done", "root": "done"}


def test_create_tasks_rejects_unknown_dependency_and_duplicates(backend):
    backend.create_tasks([{"id": "x", "title": "x"}])
    with pytest.raises(UnknownReference):
        backend.create_tasks([{"id": "y", "title": "y", "depends_on": ["ghost"]}])
    with pytest.raises(ValueError):
        backend.create_tasks([{"id": "x", "title": "again"}])
    assert [t["id"] for t in backend.list_tasks()] == ["x"]  # the failed batches wrote nothing


def test_lease_expiry_reclaims_and_heartbeat_extends(backend):
    a, b = agent(backend, "a"), agent(backend, "b")
    backend.create_tasks([{"id": "t", "title": "t"}])
    t = backend.claim_next_task(a, 1_000, now=100_000)
    assert backend.claim_next_task(b, 1_000, now=100_500) is None  # lease still valid
    assert backend.heartbeat(a, "t", 5_000, now=100_600) is True  # extends to 105_600
    assert backend.heartbeat(b, "t", 5_000, now=100_600) is False  # not the owner
    assert backend.heartbeat(a, "t", 10, now=100_700) is True  # never shortens
    assert backend.claim_next_task(b, 1_000, now=104_000) is None
    t2 = backend.claim_next_task(b, 1_000, now=106_000)
    assert t2["id"] == "t" and t2["reclaimed_from"] == a and t2["version"] == t["version"] + 1
    with pytest.raises(ClaimConflict):  # the old holder's late completion is rejected
        backend.complete_task(a, "t", t["version"])
    assert backend.complete_task(b, "t", t2["version"])["status"] == "done"


def test_complete_is_compare_and_set(backend):
    a, b = agent(backend, "a"), agent(backend, "b")
    backend.create_tasks([{"id": "t", "title": "t"}])
    t = backend.claim_next_task(a, 60_000)
    with pytest.raises(ClaimConflict):
        backend.complete_task(b, "t", t["version"])  # wrong owner
    with pytest.raises(ClaimConflict):
        backend.complete_task(a, "t", t["version"] + 7)  # stale version
    r = backend.complete_task(a, "t", t["version"], [{"id": "art-1", "kind": "file", "uri": "x.md"}])
    assert r["status"] == "done" and r["artifact_ids"] == ["art-1"]
    with pytest.raises(ClaimConflict):
        backend.complete_task(a, "t", t["version"] + 1)  # already done
    with pytest.raises(UnknownReference):
        backend.complete_task(a, "ghost", 1)


def test_claim_requires_registered_agent(backend):
    backend.create_tasks([{"id": "t", "title": "t"}])
    with pytest.raises(UnknownReference):
        backend.claim_next_task("stranger", 1_000)


def test_list_tasks(backend):
    a = agent(backend)
    backend.create_tasks([{"id": f"t{i}", "title": "t"} for i in range(3)])
    t = backend.claim_next_task(a, 60_000)
    backend.complete_task(a, t["id"], t["version"])
    rows = {r["id"]: r for r in backend.list_tasks()}
    assert (
        set(rows) == {"t0", "t1", "t2"} and rows["t0"]["status"] == "done" and rows["t1"]["status"] == "open"
    )


def test_concurrent_claims_never_double(backend):
    n_tasks, n_workers = 40, 8
    backend.create_tasks([{"id": f"t{i:03d}", "title": "t"} for i in range(n_tasks)])
    for w in range(n_workers):
        backend.register_agent(f"w{w}")
    claimed: list[tuple[str, str]] = []
    lock = threading.Lock()

    def work(w: int):
        name = f"w{w}"
        while (t := backend.claim_next_task(name, 60_000)) is not None:
            backend.complete_task(name, t["id"], t["version"])
            with lock:
                claimed.append((t["id"], name))

    threads = [threading.Thread(target=work, args=(w,)) for w in range(n_workers)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    ids = [c[0] for c in claimed]
    assert sorted(ids) == sorted(f"t{i:03d}" for i in range(n_tasks)), "every task claimed exactly once"
    assert all(r["status"] == "done" for r in backend.list_tasks())


# -- facts -----------------------------------------------------------------------------------------------------------


def test_assert_duplicate_supersede_contradiction(backend):
    a, b = agent(backend, "a"), agent(backend, "b")
    r1 = backend.assert_fact(a, "Acme API", "database", "Postgres 16", now=1_000)
    assert r1["duplicate_of"] is None and r1["superseded"] == [] and r1["contradicts"] == []

    r2 = backend.assert_fact(b, "acme  api", "Database", "postgres 16", now=2_000)  # same thing, normalised
    assert r2["duplicate_of"] == r1["fact_id"] and r2["fact_id"] == r1["fact_id"]

    # b endorsed the old value too, so a's new value cannot silently replace it: both stay, linked
    r3 = backend.assert_fact(a, "Acme API", "database", "SQLite", now=3_000)
    assert r3["contradicts"] == [r1["fact_id"]] and r3["superseded"] == []
    values = {h["value"]: h for h in backend.facts("Acme API", "database")}
    assert set(values) == {"Postgres 16", "SQLite"}
    assert values["SQLite"]["contradicts"] == [r1["fact_id"]]
    assert set(values["Postgres 16"]["asserted_by"]) == {"a", "b"}

    r4 = backend.assert_fact(b, "Acme API", "database", "MySQL", supersede=True, now=4_000)
    assert set(r4["superseded"]) == {r1["fact_id"], r3["fact_id"]} and r4["contradicts"] == []
    hist = {h["value"]: h for h in backend.facts("Acme API", "database")}
    assert hist["Postgres 16"]["status"] == "superseded" and hist["Postgres 16"]["valid_to"] == 4_000
    assert hist["MySQL"]["status"] == "active" and hist["MySQL"]["valid_to"] == OPEN
    assert set(hist["MySQL"]["supersedes"]) == {r1["fact_id"], r3["fact_id"]}


def test_own_value_change_supersedes(backend):
    a = agent(backend)
    f1 = backend.assert_fact(a, "svc", "owner", "alice", now=1_000)
    f2 = backend.assert_fact(a, "svc", "owner", "bob", now=2_000)
    assert f2["superseded"] == [f1["fact_id"]] and f2["contradicts"] == []
    hist = backend.facts("svc", "owner")
    assert [h["status"] for h in hist] == ["superseded", "active"]


def test_different_agents_contradict_and_numbers_differ(backend):
    a, b = agent(backend, "a"), agent(backend, "b")
    f1 = backend.assert_fact(a, "Acme API", "port", "8080")
    f2 = backend.assert_fact(b, "Acme API", "port", "8081")
    assert f2["contradicts"] == [f1["fact_id"]] and f2["duplicate_of"] is None
    f3 = backend.assert_fact(a, "Acme API", "version", "v1.2.3")
    f4 = backend.assert_fact(b, "Acme API", "version", "v1.2.4")
    assert f4["duplicate_of"] is None and f4["contradicts"] == [f3["fact_id"]]


def test_empty_inputs_rejected(backend):
    a = agent(backend)
    with pytest.raises(ValueError):
        backend.assert_fact(a, "", "p", "v")
    with pytest.raises(ValueError):
        backend.assert_fact(a, "s", "p", "  ")


def test_recall_finds_and_respects_scope(backend):
    a = agent(backend)
    backend.assert_fact(a, "billing service", "language", "written in Rust", scope="project:billing")
    backend.assert_fact(a, "search service", "language", "written in Haskell", scope="project:search")
    backend.assert_fact(a, "company", "motto", "ship small things often", scope="global")
    hits = backend.recall(a, "billing service language", scope="project:billing", k=5)
    texts = " | ".join(h["text"] for h in hits)
    assert "Rust" in texts and "Haskell" not in texts, texts
    inherited = " | ".join(
        h["text"] for h in backend.recall(a, "company motto", scope="project:billing", k=5)
    )
    assert "ship small things often" in inherited, "project scopes see global"
    leak = backend.recall(a, "search service language Haskell", scope="project:billing", k=10)
    assert all("Haskell" not in h["text"] for h in leak)
    assert all({"fact_id", "text", "value", "score", "status"} <= set(h) for h in hits)


def test_recall_ignores_superseded_unless_as_of(backend):
    a = agent(backend)
    backend.assert_fact(a, "deploy target", "region", "eu-west", now=1_000)
    backend.assert_fact(a, "deploy target", "region", "us-east", now=5_000)
    now_hits = backend.recall(a, "deploy target region", k=5)
    assert [h["value"] for h in now_hits] == ["us-east"]
    old = backend.recall(a, "deploy target region", k=5, as_of=2_000)
    assert [h["value"] for h in old] == ["eu-west"]


def test_as_of_time_travel(backend):
    a = agent(backend)
    for i, t in enumerate([1_000, 2_000, 3_000]):
        backend.assert_fact(a, "Acme API", "version", f"1.{i}.0", now=t)
    assert backend.as_of("Acme API", "version", 500) is None
    assert backend.as_of("acme api", "VERSION", 1_500)["value"] == "1.0.0"
    assert backend.as_of("Acme API", "version", 2_500)["value"] == "1.1.0"
    cur = backend.as_of("Acme API", "version", 99_000)
    assert cur["value"] == "1.2.0" and cur["also_valid"] == []
    assert backend.as_of("Acme API", "owner", 2_500) is None


def test_as_of_project_scope_inherits_global(backend):
    a = agent(backend)
    backend.assert_fact(a, "Acme API", "owner", "platform team", scope="global", now=1_000)
    assert backend.as_of("Acme API", "owner", 2_000, scope="project:x")["value"] == "platform team"
    backend.assert_fact(a, "Acme API", "owner", "billing team", scope="project:x", now=1_500)
    assert backend.as_of("Acme API", "owner", 2_000, scope="project:x")["value"] == "billing team"
    assert backend.as_of("Acme API", "owner", 2_000, scope="global")["value"] == "platform team"


def test_invalid_scope_rejected(backend):
    a = agent(backend)
    with pytest.raises(ValueError):
        backend.assert_fact(a, "s", "p", "v", scope="team:oops")


def test_forget_source_cascades_through_derivation(backend):
    a = agent(backend)
    s1, s2 = backend.add_source("doc://handbook"), backend.add_source("doc://wiki")
    assert backend.add_source("doc://handbook") == s1  # idempotent on uri
    f_direct = backend.assert_fact(a, "handbook", "vacation policy", "twenty five days", source_id=s1)[
        "fact_id"
    ]
    f_second = backend.assert_fact(
        a, "summary", "vacation policy summary", "generous leave", derived_from=[f_direct]
    )["fact_id"]
    f_keep = backend.assert_fact(a, "wiki", "office hours", "nine to five", source_id=s2)["fact_id"]
    assert backend.recall(a, "vacation policy", k=10)
    r = backend.forget_source(s1)
    assert set(r["fact_ids"]) == {f_direct, f_second}
    ids = {h["fact_id"] for h in backend.recall(a, "vacation policy leave days summary", k=10)}
    assert not ids & {f_direct, f_second}
    assert f_keep in {h["fact_id"] for h in backend.recall(a, "office hours", k=10)}
    assert backend.forget_source(s1)["fact_ids"] == []  # idempotent
    with pytest.raises(UnknownReference):
        backend.forget_source("no-such-source")


def test_unknown_origin_rejected_and_writes_nothing(backend):
    a = agent(backend)
    with pytest.raises(UnknownReference):
        backend.assert_fact(a, "ghost", "p", "v", source_id="nope")
    with pytest.raises(UnknownReference):
        backend.assert_fact(a, "ghost", "p", "v", derived_from=["nope"])
    assert backend.facts("ghost", "p") == []


def test_remember_episode_returns_id(backend):
    a = agent(backend)
    e1 = backend.remember_episode(a, "user asked for a notes API")
    assert e1 != backend.remember_episode(a, "user asked for tags")


# -- handoffs and decisions ----------------------------------------------------------------------------------------------


def test_handoff_and_decision_validate_references(backend):
    a, b = agent(backend, "a"), agent(backend, "b")
    backend.create_tasks([{"id": "T1", "title": "t"}])
    t = backend.claim_next_task(a, 60_000)
    done = backend.complete_task(a, "T1", t["version"], [{"id": "art1", "kind": "file", "uri": "api.md"}])
    fid = backend.assert_fact(a, "Acme API", "version", "v1")["fact_id"]
    hid = backend.handoff(a, b, "T1", "ready for build", artifact_ids=done["artifact_ids"], fact_ids=[fid])
    did = backend.record_decision(b, "T1", "use v1", [fid])
    assert hid and did and hid != did
    with pytest.raises(UnknownReference):
        backend.handoff(a, b, "T1", "x", fact_ids=["ghost"])
    with pytest.raises(UnknownReference):
        backend.handoff(a, "nobody", "T1", "x")
    with pytest.raises(UnknownReference):
        backend.handoff(a, b, "NOPE", "x")
    with pytest.raises(UnknownReference):
        backend.handoff(a, b, "T1", "x", artifact_ids=["ghost"])
    with pytest.raises(UnknownReference):
        backend.record_decision(a, "T1", "x", ["ghost"])
    assert backend.record_decision(a, "T1", "no evidence needed", [])


# -- lineage: supported or honestly Unsupported -------------------------------------------------------------------------------


def test_why_explains_decision_or_is_unsupported(backend):
    a, b = agent(backend, "a"), agent(backend, "b")
    backend.create_tasks([{"id": "T1", "title": "t"}])
    src = backend.add_source("doc://spec")
    f1 = backend.assert_fact(a, "Acme API", "version", "v1", source_id=src)["fact_id"]
    f2 = backend.assert_fact(b, "Acme API", "owner", "platform")["fact_id"]
    did = backend.record_decision(b, "T1", "ship v1", [f1, f2])
    if "why" not in backend.capabilities:
        with pytest.raises(Unsupported):
            backend.why(did)
        return
    r = backend.why(did)
    assert r["kind"] == "Decision" and r["root"] == did
    by_id = {f["id"]: f for f in r["facts"]}
    assert set(by_id) == {f1, f2}
    assert by_id[f1]["asserted_by"] == ["a"] and by_id[f2]["asserted_by"] == ["b"]
    assert by_id[f1]["sources"] == [src] and by_id[f2]["sources"] == []
    assert backend.why(f1)["kind"] == "Fact"
    with pytest.raises(UnknownReference):
        backend.why("no-such-id")


def test_knew_at_or_unsupported(backend):
    a = agent(backend, "reader")
    w = agent(backend, "writer")
    f = backend.assert_fact(w, "Acme API", "version", "v1", now=int(time.time() * 1000))["fact_id"]
    if "knew_at" not in backend.capabilities:
        with pytest.raises(Unsupported):
            backend.knew_at(a, 10)
        return
    backend.recall(a, "Acme API version", k=3)  # reader READs the fact
    cut = backend.knew_at(a, 10**6)
    assert cut["step_n"] is not None and f in {x["fact_id"] for x in cut["facts"]}
    time.sleep(0.01)
    backend.assert_fact(w, "Acme API", "version", "v2", supersede=True)
    time.sleep(0.01)
    backend.recall(a, "Acme API version", k=3)  # a later step
    earlier = backend.knew_at(a, cut["step_n"])
    assert f in {x["fact_id"] for x in earlier["facts"]}, "at the earlier step the reader still believed v1"
    later = backend.knew_at(a, 10**6)
    assert f not in {x["fact_id"] for x in later["facts"]}, "v1 was superseded before the later step"
    assert backend.knew_at("never-acted", 5)["facts"] == []


# -- tenancy ------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tenant", ["../b", "A", "a b", "a;b", "a'); MATCH (n) DETACH DELETE n //", "plexus_t_b/..", "", "x" * 49]
)
def test_invalid_tenant_names_are_rejected(arm, make_spec, tenant):
    spec = make_spec(arm, tenant)
    with pytest.raises(InvalidTenant):
        open_backend(spec)


def test_tenants_are_isolated_and_data_persists(arm, make_spec, opened):
    sa, sb = make_spec(arm), make_spec(arm)
    a1, b1 = opened(arm, sa.tenant), opened(arm, sb.tenant)
    agent(a1)
    agent(b1)
    secret = a1.assert_fact("a1", "Zephyr project", "codename", "tangerine-wolf-77")["fact_id"]
    a1.create_tasks([{"id": "only-in-a", "title": "x"}])
    assert b1.recall("a1", "Zephyr project codename tangerine-wolf-77", k=10) == []
    assert b1.task_status("only-in-a") is None and b1.list_tasks() == []
    assert b1.facts("Zephyr project", "codename") == []
    with pytest.raises(UnknownReference):
        b1.record_decision("a1", "only-in-a", "x", [secret])
    # reopening the same tenant sees the data (persistence)
    again = opened(arm, sa.tenant)
    assert [h["fact_id"] for h in again.facts("Zephyr project", "codename")] == [secret]
    assert again.task_status("only-in-a")["status"] == "open"


def test_spec_json_roundtrip(make_spec):
    s = make_spec("B1")
    assert BackendSpec.from_json(s.to_json()) == s
