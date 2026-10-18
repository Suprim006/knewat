"""Argument types and bounds shared by every MCP tool.

An LLM (or a runaway loop) controls these arguments, so every string, list and integer has an explicit bound and
the caller gets a one-line field-level error instead of a database failure:

* ids and agent ids: 1..128 chars; names (subject, predicate, role...): up to 512; uri/title: up to 2 000;
* one value: up to 20 000 chars; one free text (episode, note, decision, excerpt): up to 100 000 chars;
* lists: up to 200 items; integers inside the signed 32-bit range; epoch milliseconds up to ``OPEN``.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from knewat.common import OPEN  # "open-ended" epoch ms; also the upper bound for any caller-supplied time

MAX_ID = 128
MAX_NAME = 512
MAX_TITLE = 2_000
MAX_VALUE = 20_000
MAX_TEXT = 100_000
MAX_LIST = 200
MAX_INT = 2**31 - 1
MAX_LEASE_MS = 86_400_000  # one day
ALL_SCOPES = "all"  # recall's scope spec for every scope of the tenant graph (P12; recall only)

AgentId = Annotated[
    str,
    Field(
        description="Your stable agent id, e.g. 'planner'.",
        min_length=1,
        max_length=MAX_ID,
    ),
]
Step = Annotated[
    int | None,
    Field(
        description="Optional step counter (1, 2, 3...; never backwards): calls with the same step share one "
        "step. Omit to make each call the next step.",
        ge=1,
        le=MAX_INT,
    ),
]
ScopeArg = Annotated[
    str,
    Field(
        description="Memory scope: 'global' (shared by everyone, default), 'project:<name>' or 'user:<name>' "
        "(project/user scopes also see 'global'), or a scope id.",
        max_length=MAX_NAME,
    ),
]
LeaseMs = Annotated[
    int,
    Field(
        description="Lease length in milliseconds (max 86 400 000 = 1 day). Heartbeat before it runs out or "
        "others may take the task.",
        gt=0,
        le=MAX_LEASE_MS,
    ),
]
EpochMs = Annotated[int, Field(ge=0, le=OPEN)]
Version = Annotated[int, Field(ge=0, le=MAX_INT)]

IdStr = Annotated[str, Field(min_length=1, max_length=MAX_ID)]
Name = Annotated[str, Field(max_length=MAX_NAME)]
NameReq = Annotated[str, Field(min_length=1, max_length=MAX_NAME)]
Title = Annotated[str, Field(min_length=1, max_length=MAX_TITLE)]
Short = Annotated[str, Field(max_length=MAX_TITLE)]
Value = Annotated[str, Field(max_length=MAX_VALUE)]
Text = Annotated[str, Field(max_length=MAX_TEXT)]
TextReq = Annotated[str, Field(min_length=1, max_length=MAX_TEXT)]


class StrictModel(BaseModel):
    """A tool argument object that refuses unknown keys, naming the keys that are expected.

    Silently dropping a misspelt key (``dependsOn`` for ``depends_on``) would create a task without its
    dependency, so an unknown key is an error.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            unknown = sorted(str(k) for k in data if k not in cls.model_fields)
            if unknown:
                expected = ", ".join(cls.model_fields)
                raise ValueError(
                    f"unknown key(s) {', '.join(repr(k[:40]) for k in unknown[:5])}; expected keys: {expected}"
                )
        return data
