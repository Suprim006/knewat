"""Run configuration for the Crucible layers (full run vs ``--quick``)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

L1_ARMS = ("B0", "B1", "B2", "P")
L4_ARMS = ("B0", "B1", "B2", "P", "P-mcp")


@dataclass
class L1Config:
    reps: int = 10
    base_seed: int = 1000
    arms: tuple[str, ...] = L1_ARMS
    tests: tuple[str, ...] = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8")
    c1_workers: tuple[int, ...] = (10, 50, 100, 200)
    c1_tasks: int = 500
    c2_tasks: int = 12
    c2_victims: int = 3
    c2_survivors: int = 4
    c2_lease_ms: int = 1500
    c2_heartbeat_ms: int = 500
    c2_poll_ms: int = 25
    c3_same_value_agents: int = 20
    c3_conflicting_agents: int = 8
    c4_layers: tuple[int, ...] = (1, 3, 9, 27, 81)  # depth 5, fan-out 3
    c4_workers: int = 20
    c5_workers: int = 8
    c6_subjects: int = 10
    c6_versions: int = 5
    c6_queries: int = 20
    c6_workers: int = 5
    c7_pairs: int = 100  # use every pair in the corpus (capped by its size)
    c8_sources: int = 5
    c8_facts_per_source: int = 8
    c8_forgotten_sources: int = 2

    @property
    def seeds(self) -> list[int]:
        return [self.base_seed + i for i in range(self.reps)]

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["seeds"] = self.seeds
        return d


def quick_l1() -> L1Config:
    return L1Config(
        reps=2,
        c1_workers=(10, 50),
        c1_tasks=100,
        c2_tasks=6,
        c2_victims=2,
        c2_survivors=3,
        c2_lease_ms=1000,
        c2_heartbeat_ms=300,
        c3_same_value_agents=8,
        c3_conflicting_agents=4,
        c4_layers=(1, 3, 9, 27),
        c4_workers=8,
        c5_workers=4,
        c6_subjects=4,
        c6_versions=4,
        c6_queries=10,
        c6_workers=4,
        c8_sources=3,
        c8_facts_per_source=4,
        c8_forgotten_sources=1,
    )


@dataclass
class L4Config:
    arms: tuple[str, ...] = L4_ARMS
    workers: tuple[int, ...] = (1, 10, 50, 100, 200)
    ops_per_worker: int = 12  # claim -> heartbeat -> complete cycles per worker (claim phase)
    max_cycles: int = 1500  # cap on total claim cycles per point (tasks created per point)
    recall_facts: int = 300
    recall_per_worker: int = 10
    max_recalls: int = 1500
    tenant_workers: int = 50  # one graph vs N graphs: workers and tenant counts
    tenant_counts: tuple[int, ...] = (1, 4, 16)
    tenant_ops_per_worker: int = 12
    tenant_arms: tuple[str, ...] = ("B1", "P")
    recall_arms: tuple[str, ...] = ("B0", "B1", "B2", "P", "P-mcp")
    seed: int = 4242
    lease_ms: int = 600_000
    point_timeout_s: float = 240.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def quick_l4() -> L4Config:
    return L4Config(
        workers=(1, 10, 25),
        ops_per_worker=6,
        max_cycles=300,
        recall_facts=60,
        recall_per_worker=4,
        max_recalls=200,
        tenant_workers=16,
        tenant_counts=(1, 4),
        tenant_ops_per_worker=6,
        point_timeout_s=90.0,
    )


@dataclass
class Meta:
    """Free-form facts about the run environment recorded next to the config."""

    values: dict[str, Any] = field(default_factory=dict)
