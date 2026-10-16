"""Lineage attachment for a tool call: open the agent's ``Step``, link its ``WROTE`` / ``READ`` edges, run the hook.

Everything here is best effort. The tool's own write has already happened by the time these run, so a Lineage
failure never fails the call: it is logged, noted in the ``degraded`` list (the runtime then reports
``lineage_degraded``) and the call goes on.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterable, Iterator
from typing import Any

from redis.exceptions import RedisError

from plexus.graph.client import GraphClient
from plexus.mcp.metering import MeteredClient, Outcome
from plexus.mcp.tenant import TenantState

log = logging.getLogger("plexus.mcp")  # stderr only: stdout is the stdio protocol channel

WROTE_LABELS = frozenset(
    {"Decision", "Handoff", "Task"}
)  # nodes a Step can WROTE besides Facts (see link_step)
HOOK_NODE_KEYS = {"recall_id": "Recall"}  # keys an Outcome.after hook may return -> label of the node it made
# Tools whose write statement creates (Step)-[:WROTE]->(node) itself (P9-int, L6-F; the five task tools: P12 fix 2):
# the Runtime opens their Step BEFORE the tool runs and hands it over as ``MeteredClient.step_id``. A crash can then
# no longer leave the new fact / decision / handoff / task change without its WROTE edge. Every other tool is
# still linked after its write.
FOLDS_WROTE = frozenset(
    {
        "assert_fact",
        "record_decision",
        "handoff",
        "create_tasks",
        "claim_next_task",
        "complete_task",
        "fail_task",
        "reopen_task",
    }
)
# Relay tools whose own statement MATCHes the acting agent and rejects an unknown one ("unknown agent"). Opening the
# Step first would MERGE that agent into existence (lineage/record_step), so for these the early Step is skipped when
# the agent is not registered: the tool then fails exactly as before and no Step or Agent is left behind.
REQUIRES_AGENT = FOLDS_WROTE - {"assert_fact"}
LINK_CHUNK = 200  # ids per link_step call (lineage.MAX_LINK_IDS)


@contextlib.contextmanager
def _degrade_on_error(degraded: list[str], kind: str, message: str, *args: Any) -> Iterator[None]:
    """Log an exception and record ``kind`` in ``degraded`` instead of letting it fail the call."""
    try:
        yield
    except Exception:
        log.exception(message, *args)
        degraded.append(kind)


def open_step(
    client: GraphClient, ts: TenantState, agent_id: str, step: int | None, at: int, degraded: list[str]
) -> str | None:
    """The agent's Step for this call (get-or-create by (agent, n)); ``None`` without Lineage.

    An explicit ``step`` is respected (the same ``n`` always maps to the same Step). Without one the next
    number is used (previous + 1), so every call is attributable. A ``step`` behind the agent's latest one
    cannot be recorded (the NEXT chain is append-only): the call then takes the next number instead.
    """
    lin = ts.lineage(MeteredClient(client))
    if lin is None:
        return None
    with _degrade_on_error(degraded, "step", "lineage: could not record a Step for %s", agent_id):
        try:
            return lin.record_step(agent_id, step, at)
        except ValueError:  # StepOrderError
            if step is None:
                raise
            log.warning("step %s is behind %s's latest step; using the next number", step, agent_id)
            return lin.record_step(agent_id, None, at)
    return None


def open_pre_step(
    client: GraphClient,
    ts: TenantState,
    tool: str,
    agent_id: str,
    step: int | None,
    at: int,
    degraded: list[str],
) -> str | None:
    """The Step opened BEFORE a FOLDS_WROTE tool runs; ``None`` when the tool needs a registered agent and it is not."""
    if tool in REQUIRES_AGENT and not client.ro(ts.graph, "relay/agent_exists", {"id": agent_id}):
        return None
    return open_step(client, ts, agent_id, step, at, degraded)


def discard_step(client: GraphClient, ts: TenantState, step_id: str | None) -> None:
    """Best effort: remove the Step opened for a call that failed before writing anything (see ``Runtime._run``)."""
    if step_id is None:
        return
    try:
        lin = ts.lineage(MeteredClient(client))
        if lin is not None:
            lin.discard_step(step_id)
    except Exception:
        log.exception("lineage: could not discard the empty step %s", step_id)


def attach(
    client: GraphClient, ts: TenantState, step_id: str | None, out: Outcome, degraded: list[str]
) -> dict[str, Any]:
    """Attach WROTE / READ edges and run the tool's ``after`` hook; returns what the hook adds to the result."""
    extra: dict[str, Any] = {}
    if step_id is None:
        return extra
    lin = ts.lineage(MeteredClient(client))
    if lin is None:
        return extra
    done = set(out.linked)  # WROTE edges the write statement itself already created
    wrote = _ids(i for label, i in (*out.created, *out.updated) if label in WROTE_LABELS and i not in done)
    read = _ids(out.read_ids)

    def link() -> None:
        if out.assert_result is not None:
            lin.link_assert_result(
                step_id, out.assert_result, wrote_linked=out.assert_result["fact_id"] in done
            )
        for i in range(0, max(len(wrote), len(read)), LINK_CHUNK):
            lin.link_step(step_id, wrote_ids=wrote[i : i + LINK_CHUNK], read_ids=read[i : i + LINK_CHUNK])

    with _degrade_on_error(degraded, "link", "lineage: could not link step %s", step_id):
        try:
            link()
        except (RedisError, OSError):  # transient: every link statement is idempotent, so try once more
            log.warning("lineage: retrying link_step for %s", step_id)
            link()
    if out.after is not None:
        with _degrade_on_error(degraded, "after", "lineage: after-hook failed for step %s", step_id):
            extra = out.after(lin, step_id) or {}
    return extra


def _ids(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))
