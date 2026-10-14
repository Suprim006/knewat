"""The scheduler shared by the scripted agents and the real ``claude -p`` orchestrator.

One turn at a time (round-robin by readiness): the scheduler looks at the ready tasks, picks the top one (the
same order ``claim_next_task`` uses, so the agent's claim gets exactly that task), hands the turn to the agent
whose role the task is for, and applies the fault script at call and turn boundaries. A *driver* plays a turn:
``plexus.demo.scripted.ScriptedDriver`` calls the MCP tools from code, ``plexus.demo.orchestrator.ClaudeDriver``
starts a ``claude -p`` process. Both count tool calls on the same global step counter, which is what the fault
script keys on ("step 15" = the 15th Plexus tool call of the run, whichever agent made it).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from plexus.demo.scenario import FaultScript, Scenario, TaskDef
from plexus.graph.client import GraphClient
from plexus.graph.tenancy import graph_name
from plexus.relay import Relay

BUILDER = "builder"


class AgentKilled(Exception):
    """The fault script killed an agent mid-task; its claim is left to expire."""

    def __init__(self, agent: str, task_id: str):
        super().__init__(f"{agent} was killed while holding {task_id}")
        self.agent = agent
        self.task_id = task_id


class SchedulerStuck(RuntimeError):
    pass


@dataclass
class Turn:
    kind: str  # 'init' | 'task' | 'special'
    agent: str
    name: str  # task id, special name, or 'init'
    task: TaskDef | None = None
    reclaim_from: str = ""  # previous claimer when this turn takes over an expired lease


@dataclass
class World:
    """Everything one run shares: the DB handle, the global step counter, fault state and the event log."""

    scenario: Scenario
    faults: FaultScript
    tenant: str
    client: GraphClient
    pace_s: float = 0.0  # seconds to sleep before each tool call (live viewing)
    step: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)  # {step, agent, tool}
    holds: dict[str, str] = field(default_factory=dict)  # agent -> task id it has claimed and not finished
    dead: set[str] = field(default_factory=set)
    pending: list[Turn] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    on_call: Any = None  # optional callback(dict) after every counted tool call (live output)

    def __post_init__(self) -> None:
        self.graph = graph_name(self.tenant)
        self.relay = Relay(self.client, self.graph)

    # -- bookkeeping ---------------------------------------------------------------------------------------
    def event(self, name: str, **info: Any) -> dict[str, Any]:
        ev = {"event": name, "step": self.step, "t": round(time.time() - self.started_at, 3), **info}
        self.events.append(ev)
        return ev

    def count_call(self, agent: str, tool: str) -> int:
        self.step += 1
        rec = {"step": self.step, "agent": agent, "tool": tool}
        self.calls.append(rec)
        if self.on_call is not None:
            self.on_call(rec)
        return self.step

    # -- fault hooks ---------------------------------------------------------------------------------------
    def should_kill(self, agent: str) -> bool:
        """True (once) if ``agent`` is the builder, holds a claimed task and the kill step has been reached."""
        f = self.faults
        if (
            agent != BUILDER
            or agent not in self.holds
            or not f.due("kill_builder", f.kill_builder_at, self.step)
        ):
            return False
        f.fire("kill_builder", self.step)
        self.dead.add(agent)
        self.event("kill_builder", agent=agent, task=self.holds[agent], lease_ms=f.builder_lease_ms)
        return True

    def boundary(self) -> None:
        """Turn boundary: fire the time-based faults that came due (they queue special turns)."""
        f = self.faults
        if f.due("publish_v2", f.publish_v2_at, self.step):
            f.fire("publish_v2", self.step)
            self.event("publish_v2", doc="06_api_style_guide_v2")
            self.pending += [self._special("ingest-v2"), self._special("adopt-v2")]
        if f.due("poison", f.poison_at, self.step):
            f.fire("poison", self.step)
            self.event("poison_source", doc="07_forum_post_unverified")
            self.pending += [self._special("ingest-forum-post"), self._special("quarantine-forum-post")]

    def _special(self, name: str) -> Turn:
        return Turn("special", self.scenario.specials[name].role, name)

    # -- reading the task state (the harness peeks at the DB; agents only use MCP tools) --------------------
    def ready(self) -> list[dict[str, Any]]:
        return self.relay.ready_tasks(limit=50)

    def statuses(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for t in self.scenario.all_tasks:
            st = self.relay.task_status(t.id)
            if st is not None:
                out[t.id] = st
        return out

    def next_lease_expiry(self) -> int | None:
        """Earliest ``lease_until`` (epoch ms) among claimed tasks, or None."""
        leases = [s["lease_until"] for s in self.statuses().values() if s["status"] == "claimed"]
        return min(leases) if leases else None

    async def pace(self) -> None:
        if self.pace_s > 0:
            await asyncio.sleep(self.pace_s)


class Driver(Protocol):
    async def run_turn(self, w: World, turn: Turn) -> None: ...


def reclaimer_for(w: World, previous: str) -> str:
    """Who takes over a task whose claimer disappeared: the researcher, or the planner if it was the researcher."""
    pick = w.faults.reclaimer
    return "planner" if previous == pick else pick


async def run(w: World, driver: Driver, max_turns: int = 60) -> World:
    """Play the scenario to the end with ``driver``. Returns the world (events, calls, fired faults)."""
    init = Turn("init", "planner", "init")
    w.turns.append(init)
    await driver.run_turn(w, init)
    for _ in range(max_turns):
        w.boundary()
        if w.pending:
            turn = w.pending.pop(0)
        else:
            ready = w.ready()
            if not ready:
                lease = w.next_lease_expiry()
                if (
                    lease is not None
                ):  # something is still claimed: wait for its lease, then it is reclaimable
                    await _sleep_until_ms(lease)
                    continue
                _assert_all_done(w)
                return w
            top = ready[0]
            task = w.scenario.task(top["id"])
            reclaim_from = top["claimed_by"] if top["status"] == "claimed" else ""
            agent = reclaimer_for(w, reclaim_from) if reclaim_from else task.role
            turn = Turn("task", agent, task.id, task=task, reclaim_from=reclaim_from)
            if reclaim_from:
                w.event("reclaim", task=task.id, agent=agent, reclaimed_from=reclaim_from)
        w.turns.append(turn)
        try:
            await driver.run_turn(w, turn)
        except AgentKilled as k:
            lease = w.next_lease_expiry()
            w.event("lease_wait", task=k.task_id, until_ms=lease)
            if lease is not None:
                await _sleep_until_ms(lease)
        else:
            if turn.reclaim_from:
                w.dead.discard(turn.reclaim_from)  # the dead agent is restarted after the takeover
    raise SchedulerStuck(f"scenario did not finish within {max_turns} turns")


async def _sleep_until_ms(epoch_ms: int, margin_ms: int = 60) -> None:
    delay = (epoch_ms + margin_ms) / 1000 - time.time()
    if delay > 0:
        await asyncio.sleep(delay)


def _assert_all_done(w: World) -> None:
    left = [tid for tid, s in w.statuses().items() if s["status"] != "done"]
    if left:
        raise SchedulerStuck(f"no task is ready but these are not done: {left}")
