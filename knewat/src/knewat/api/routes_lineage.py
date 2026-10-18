"""Lineage-backed routes: ``/api/{tenant}/step/{n}``, ``/why/{node_id}`` and ``/recall/{recall_id}``."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Path as PathParam
from redis.exceptions import RedisError, ResponseError

from knewat.api import models as M
from knewat.api.context import ApiContext, activation_props, is_missing_graph, log
from knewat.common import OPEN
from knewat.lineage import Lineage

MAX_ID = 128


def router(ctx: ApiContext) -> APIRouter:
    r = APIRouter()

    def lineage(tenant: str) -> Lineage:
        """A ``Lineage`` bound to the tenant graph over the read-only client (it cannot write)."""
        return Lineage(ctx.ro, ctx.graph_of(tenant))

    def explain(tenant: str, method: str, arg: Any, model: Any, ident: str):
        try:
            result = getattr(lineage(tenant), method)(arg)
        except (LookupError, ValueError) as exc:
            raise HTTPException(404, str(exc)) from None
        except ResponseError as exc:
            if is_missing_graph(exc):
                raise HTTPException(404, f"unknown tenant '{tenant}'") from None
            log.exception("%s failed", method)
            raise HTTPException(502, "the graph database rejected the query") from None
        except (RedisError, OSError):
            log.exception("database unreachable")
            raise HTTPException(503, "graph database unavailable") from None
        data = json.loads(json.dumps(result, default=str))
        # Fact nodes in the explanation carry the same activation fields as the explorer's nodes
        nodes = data.get("nodes") or []
        act = ctx.activations(tenant, [n["id"] for n in nodes if n.get("label") == "Fact"])
        for n in nodes:
            if n.get("label") == "Fact" and n["id"] in act:
                n.setdefault("props", {}).update(activation_props(act[n["id"]]))
        return model(id=ident, result=data)

    @r.get("/api/{tenant}/step/{n}", response_model=M.StepResponse)
    def step(tenant: str, n: int = PathParam(ge=0, le=OPEN)):
        """What each agent knew and wrote at its latest step <= n: ``Lineage.knew_at`` per agent."""
        lin = lineage(tenant)
        agents: list[M.StepAgent] = []
        for row in ctx.run(tenant, "view/step_agents", {"n": n}):
            try:
                k = lin.knew_at(row["agent_id"], n)
            except (RedisError, OSError):
                log.exception("database unreachable")
                raise HTTPException(503, "graph database unavailable") from None
            if k["step_n"] is None:
                continue
            agents.append(
                M.StepAgent(
                    agent_id=k["agent_id"],
                    step_n=k["step_n"],
                    step_at=k["at"],
                    read=[
                        M.StepFact(
                            id=f["fact_id"],
                            entity=f["entity"],
                            predicate=f["predicate"],
                            value=f["value"],
                            status=f["status"],
                            valid_from=f["valid_from"],
                            valid_to=f["valid_to"],
                            read_at_step=f["read_at_step"],
                        )
                        for f in k["facts"]
                    ],
                    wrote=[
                        M.StepWrote(id=w["id"], label=w["label"], summary=w["summary"], step_n=w["step_n"])
                        for w in k["wrote"]
                    ],
                )
            )
        return M.StepResponse(n=n, agents=agents)

    @r.get("/api/{tenant}/why/{node_id}", response_model=M.WhyResponse)
    def why(tenant: str, node_id: str = PathParam(min_length=1, max_length=MAX_ID)):
        """``Lineage.why`` for a decision or fact id."""
        return explain(tenant, "why", node_id, M.WhyResponse, node_id)

    @r.get("/api/{tenant}/recall/{recall_id}", response_model=M.RecallResponse)
    def recall_record(tenant: str, recall_id: str = PathParam(min_length=1, max_length=MAX_ID)):
        """``Lineage.why_recalled`` for a recall id (the recall tool returns it as ``recall_id``)."""
        return explain(tenant, "why_recalled", recall_id, M.RecallResponse, recall_id)

    return r
