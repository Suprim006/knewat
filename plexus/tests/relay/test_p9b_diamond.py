"""P9-b / P1: ``blocked_by_failure`` on a diamond task DAG (145 tasks, 8 levels, fan-in 3) stays linear."""

from __future__ import annotations

from plexus.relay import Relay
from tests.lineage.diamond import TimedClient, build_tasks


def test_blocked_by_failure_145_tasks_8_levels_fan_in_3_under_100ms_server_time(client, graph, clock):
    tc = TimedClient(client)
    relay = Relay(tc, graph, clock=clock)
    layers = build_tasks(relay, levels=8, width=18, fan_in=3)
    assert sum(len(layer) for layer in layers) == 145
    tc.reset()
    got = relay.blocked_by_failure("root")
    assert len(got) == 144 and len(set(got)) == 144
    assert got[:18] == sorted(layers[1])  # nearest first
    assert tc.server_ms < 100, (tc.server_ms, tc.calls)


def test_dependents_of_is_one_hop_distinct(client, graph, clock):
    relay = Relay(client, graph, clock=clock)
    layers = build_tasks(relay, levels=3, width=6, fan_in=3)
    rows = client.ro(graph, "relay/dependents_of", {"frontier": layers[1]})
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))  # a task depending on several frontier members appears once
    assert set(ids) <= set(layers[2])


def test_blocked_by_failure_walks_a_24_level_dag_past_the_old_10_level_cap(client, graph, clock):
    # BEAT_SQL Probe A shape: 24 layers of 6 tasks, each depending on 2 below = 2**24 paths, 145 tasks
    tc = TimedClient(client)
    relay = Relay(tc, graph, clock=clock)
    layers = build_tasks(relay, levels=24, width=6, fan_in=2)
    tc.reset()
    got = relay.blocked_by_failure("root")
    assert len(got) == 144 and got[-6:] == sorted(layers[-1])
    assert tc.server_ms < 100, (tc.server_ms, tc.calls)
    assert (
        len(relay.blocked_by_failure("root", depth=3)) == 18
    )  # optional depth bound: layers 1..3 (the root's 2 children + their layers)
