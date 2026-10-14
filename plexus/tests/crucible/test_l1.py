"""L1 harness tests: every arm passes the quick suite, and deliberately broken arms are caught (negative controls)."""

from __future__ import annotations

import time

import pytest

from plexus.crucible.api import BackendSpec
from plexus.crucible.backends import register_arm
from plexus.crucible.backends.sqlite import SqliteBackend
from plexus.crucible.config import quick_l1
from plexus.crucible.harness import Env
from plexus.crucible.l1 import TESTS, run_test
from plexus.crucible.util import now_ms

from .conftest import ARMS, DB_HOST, DB_PORT


@pytest.fixture
def env(tmp_path, embedder_kind):
    return Env(root=str(tmp_path / "root"), host=DB_HOST, port=DB_PORT, embedder=embedder_kind)


@pytest.fixture
def cfg():
    c = quick_l1()
    c.reps = 1
    return c


@pytest.mark.parametrize("test", sorted(TESTS))
@pytest.mark.parametrize("arm", ARMS)
def test_quick_l1_is_green_for_every_arm(arm, test, env, cfg):
    r = run_test(env, arm, test, cfg, log=lambda _: None)
    assert r["runs"] >= 1
    assert r["passed"], (r["violations_total"], [d["errors"] for d in r["runs_detail"]])


# -- negative controls: the harness must notice real bugs ---------------------------------------------------------------------


class Racy(SqliteBackend):
    """Check-then-act claim: reads the open task outside any write transaction."""

    name = "X-race"

    def claim_next_task(self, agent_id, lease_ms=60_000, now=None):
        t = now if now is not None else now_ms()
        with self._conn() as c:
            row = c.execute(
                "SELECT id, title, priority, version FROM tasks WHERE status='open' ORDER BY priority DESC, seq LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        time.sleep(0.002)
        with self._tx() as c:
            c.execute(
                "UPDATE tasks SET status='claimed', claimed_by=?, lease_until=?, version=version+1 WHERE id=?",
                (agent_id, t + lease_ms, row["id"]),
            )
        return {
            "id": row["id"],
            "title": row["title"],
            "priority": row["priority"],
            "version": row["version"] + 1,
            "lease_until": t + lease_ms,
            "reclaimed_from": "",
        }


class IgnoresDeps(SqliteBackend):
    name = "X-nodeps"

    def claim_next_task(self, agent_id, lease_ms=60_000, now=None):
        t = now if now is not None else now_ms()
        with self._tx() as c:
            row = c.execute(
                "SELECT id, title, priority, version FROM tasks WHERE status='open' ORDER BY priority DESC, seq LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            c.execute(
                "UPDATE tasks SET status='claimed', claimed_by=?, lease_until=?, version=version+1 WHERE id=?",
                (agent_id, t + lease_ms, row["id"]),
            )
        return {
            "id": row["id"],
            "title": row["title"],
            "priority": row["priority"],
            "version": row["version"] + 1,
            "lease_until": t + lease_ms,
            "reclaimed_from": "",
        }


class Leaky(SqliteBackend):
    """Every tenant shares one database file: no isolation."""

    name = "X-leaky"

    def __init__(self, tenant, root):
        super().__init__("shared", root)
        self.tenant = tenant


class NoCascade(SqliteBackend):
    """Forgets only facts attached directly to the source, not facts derived from them."""

    name = "X-nocascade"

    def forget_source(self, source_id):
        t = now_ms()
        with self._tx() as c:
            ids = [
                r["src"]
                for r in c.execute(
                    "SELECT src FROM fact_links WHERE dst=? AND kind='derived_from'", (source_id,)
                )
            ]
            ids = [i for i in ids if c.execute("SELECT 1 FROM facts WHERE id=?", (i,)).fetchone()]
            for i in ids:
                c.execute("UPDATE facts SET status='forgotten', valid_to=MIN(valid_to, ?) WHERE id=?", (t, i))
        return {"source_id": source_id, "fact_ids": sorted(ids)}


class LatestOnly(SqliteBackend):
    """as_of ignores the validity window and answers with the current value."""

    name = "X-latest"

    def as_of(self, subject, predicate, t, scope="global"):
        return super().as_of(subject, predicate, 9_999_999_999_000, scope)


def _register(name, cls):
    register_arm(name, lambda spec: cls(spec.tenant, spec.root))


@pytest.fixture
def broken():
    names = []

    def add(cls):
        _register(cls.name, cls)
        names.append(cls.name)
        return cls.name

    yield add
    for n in names:
        register_arm(n, None)


@pytest.mark.parametrize(
    ("cls", "test", "violation"),
    [
        (Racy, "C1", "double_claims"),
        (IgnoresDeps, "C4", "started_before_deps_done"),
        (Leaky, "C5", "rows_leaked"),
        (NoCascade, "C8", "derived_facts_still_returned"),
        (LatestOnly, "C6", "wrong_version_answers"),
    ],
)
def test_harness_catches_broken_arms(cls, test, violation, broken, env, cfg):
    arm = broken(cls)
    r = run_test(env, arm, test, cfg, log=lambda _: None)
    assert not r["passed"]
    assert r["violations_total"].get(violation, 0) > 0, r["violations_total"]


def test_spec_arms_are_registered():
    from plexus.crucible.backends import open_backend

    with pytest.raises(ValueError):
        open_backend(BackendSpec(arm="nope", tenant="t", root="."))
