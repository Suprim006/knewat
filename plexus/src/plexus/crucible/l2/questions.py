"""The Layer 2 question set: ~40 exact-match questions whose ground truth is computed from the scenario ledger.

Every question carries:

* ``text`` and ``format``: all an LLM arm sees (plus the shared conventions in :data:`CONVENTIONS`);
* ``kind``: ``set`` (order-insensitive list), ``ordered`` (list), ``value`` (one string), ``yesno`` or ``int``;
* ``item``: how items are normalised before comparing (``fact`` = ``predicate=value``, ``decision`` = first four
  words, ``task``/``agent``/``artifact``/``source``/``scope``/``text``/``value``/``predicate`` = case-folded string,
  ``fact_by`` = ``fact @ agent``);
* ``answer``: the ground truth, derived from the ledger (never typed by hand);
* ``op`` / ``args``: the deterministic query the Plexus arm runs (``plexus_answerer``); LLM arms never see them.

There is no LLM judge: :func:`score` is a normalised string comparison.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from plexus.crucible.l2.scenario import (
    ACME_SCOPE,
    BILLING_SCOPE,
    BILLING_SUBJECT,
    Ledger,
    decision_label,
)

FAMILIES: dict[str, str] = {
    "decision_provenance": "Decision provenance",
    "handoffs": "Handoffs",
    "time_travel": "Time travel",
    "supersession": "Supersession impact",
    "dependencies": "Dependencies",
    "contradictions": "Contradictions",
    "recovery": "Recovery",
    "memory_scope": "Memory currency and scope",
    "episodes": "Cross-session recall",
    "forgetting": "Forgetting",
}

CONVENTIONS = """\
Conventions for every question:
- Time is epoch milliseconds. A fact is valid at time t when valid_from <= t < valid_to.
- A fact is named `predicate=value` (for example `api_version=v1`). A fact is "current" when its status is active
  (not superseded and not forgotten).
- A decision is named by the first four words of its text, lower case, without punctuation.
- Tasks are named by their task id (for example `t03-design-endpoints`), agents by their id (planner, researcher,
  builder), artifacts by their uri, sources by their uri.
- Answer with ONE JSON object and nothing else: {"answer": <value>}, in the format the question asks for."""


@dataclass
class Question:
    id: str
    family: str
    text: str
    format: str
    kind: str
    item: str
    answer: Any
    op: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> Question:
        return cls(**d)

    def prompt(self) -> str:
        return f"Question {self.id}: {self.text}\nAnswer format: {self.format}"


# ------------------------------------------------------------------------------------------------ normalisation
_WS = re.compile(r"\s+")


def _clean(s: Any) -> str:
    s = _WS.sub(" ", str(s).strip()).casefold().strip(" .;,")
    return s


def _fact(s: Any) -> str:
    s = _clean(s)
    s = re.sub(r"\s*=\s*", "=", s)
    return s.strip("`\"' ")


def _norm_item(item: str, s: Any) -> str:
    if item == "decision":
        return decision_label(str(s))
    if item == "fact":
        return _fact(s)
    if item == "fact_by":
        left, _, right = str(s).rpartition("@")
        return f"{_fact(left)}@{_clean(right)}"
    return _clean(s).strip("`\"' ")


def normalise(q: Question, answer: Any) -> Any:
    """Canonical form of an answer (ground truth or model output) for the question's ``kind``/``item``."""
    if q.kind in ("set", "ordered"):
        if isinstance(answer, str) or not isinstance(answer, Iterable):
            raise ValueError("a list was expected")
        items = [_norm_item(q.item, x) for x in answer]
        return sorted(set(items)) if q.kind == "set" else items
    if q.kind == "yesno":
        s = _clean(answer)
        if s in ("yes", "true"):
            return "yes"
        if s in ("no", "false"):
            return "no"
        raise ValueError("yes or no was expected")
    if q.kind == "int":
        if isinstance(answer, bool):
            raise ValueError("an integer was expected")
        if isinstance(answer, int | float) and int(answer) == answer:
            return int(answer)
        if isinstance(answer, str) and answer.strip().isdigit():
            return int(answer.strip())
        raise ValueError("an integer was expected")
    if isinstance(answer, list | dict):
        raise ValueError("a single string was expected")
    return _norm_item(q.item, answer)


def score(q: Question, got: Any) -> tuple[bool, str]:
    """Exact match after normalisation. Returns ``(correct, why_not)``."""
    try:
        return normalise(q, got) == normalise(q, q.answer), ""
    except ValueError as exc:
        return False, f"unparseable answer: {exc}"


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)
_ANSWER_OBJ = re.compile(r'\{\s*"answer"\s*:')
_DECODER = json.JSONDecoder()


def parse_reply(text: str, *, strict: bool = False) -> tuple[Any, str]:
    """Parse a model reply into its ``{"answer": ...}`` object.

    ``strict=True``: the whole reply (optionally in one code fence) must be exactly that JSON object.
    ``strict=False`` (the scoring rule): the reply may start with reasoning prose, but its **last** ``{"answer": ...}``
    must be valid JSON of exactly that shape and nothing but whitespace or a closing fence may follow it.
    """
    s = text.strip()
    m = _FENCE.match(s)
    if m:
        s = m.group(1).strip()
    if not strict and not s.startswith("{"):
        hits = list(_ANSWER_OBJ.finditer(s))
        if not hits:
            return None, 'no {"answer": ...} object in the reply'
        s = s[hits[-1].start() :]
    try:
        obj, end = _DECODER.raw_decode(s)
    except json.JSONDecodeError as exc:
        return None, f"reply is not JSON: {exc.msg}"
    if s[end:].strip().strip("`").strip():
        return None, "text after the JSON object"
    if not isinstance(obj, dict) or set(obj) != {"answer"}:
        return None, 'reply must be exactly {"answer": ...}'
    return obj["answer"], ""


# ------------------------------------------------------------------------------------------------ building
def _dedupe(xs: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(xs))


def _downstream(led: Ledger, task_id: str) -> list[str]:
    deps_of: dict[str, list[str]] = {}
    for t in led.tasks:
        for d in t["depends_on"]:
            deps_of.setdefault(d, []).append(t["id"])
    seen: list[str] = []
    stack = [task_id]
    while stack:
        for nxt in deps_of.get(stack.pop(), []):
            if nxt not in seen:
                seen.append(nxt)
                stack.append(nxt)
    return sorted(seen)


def _facts_at(led: Ledger, subject: str, predicate: str, t: int) -> list[dict[str, Any]]:
    """Facts valid at ``t`` according to the script: asserted at or before t and not superseded before t."""
    out = []
    for f in led.facts:
        if f["subject"] != subject or f["predicate"] != predicate or f["scope"] != "global":
            continue
        if f["t"] > t:
            continue
        gone = [g["t"] for g in led.facts if f["label"] in g["superseded"] and g["subject"] == subject]
        if gone and min(gone) <= t:
            continue
        out.append(f)
    return out


def _decisions_on(led: Ledger, labels: set[str]) -> list[str]:
    return [d["label"] for d in led.decisions if labels & set(d["fact_labels"])]


class _Builder:
    """State shared by the per-family question builders: the ledger, the questions so far, and the facts that
    several families refer to. Ids are assigned in order (``Q01``, ``Q02``, ...) as questions are added."""

    def __init__(self, led: Ledger):
        self.led = led
        self.qs: list[Question] = []
        self.subj = led.subject
        self.v1, self.v2 = led.fact("api_version=v1"), led.fact("api_version=v2")
        self.jwt = led.fact("auth_method=JWT bearer tokens (RS256)")
        self.key = led.fact("auth_method=API key in X-Api-Key header")
        self.mongo = led.fact("database=MongoDB 4")
        self.pg = led.fact("database=PostgreSQL 16")
        self.superseded = {
            f["label"] for f in led.facts if any(f["label"] in g["superseded"] for g in led.facts)
        }
        self.forgotten = _dedupe(x for fg in led.forgotten for x in fg["fact_labels"])
        self.fmt_facts = 'a JSON list of fact names, e.g. ["predicate=value"]'

    def add(
        self, family: str, text: str, fmt: str, kind: str, item: str, answer: Any, op: str, **args: Any
    ) -> None:
        self.qs.append(Question(f"Q{len(self.qs) + 1:02d}", family, text, fmt, kind, item, answer, op, args))


def _decision_provenance(b: _Builder) -> None:
    led, add, fmt_facts = b.led, b.add, b.fmt_facts
    d_jwt = led.decision("use jwt bearer tokens")
    d_v1 = led.decision("build the acme notes")
    d_ok = led.decision("spec approved endpoints schema")
    d_mongo = led.decision("evaluate mongodb 4 as")
    d_pg = led.decision("use postgresql 16 for")
    fmt_facts = 'a JSON list of fact names, e.g. ["predicate=value"]'
    for d in (d_jwt, d_v1, d_ok, d_mongo):
        add(
            "decision_provenance",
            f'Which facts was the decision "{d["text"]}" based on?',
            fmt_facts, "set", "fact", d["fact_labels"], "decision_facts", decision=d["label"],
        )  # fmt: skip
    by = {f["label"]: f["agent"] for f in led.facts}
    add(
        "decision_provenance",
        f'For each fact that the decision "{d_jwt["text"]}" was based on, which agent asserted it?',
        'a JSON list of "fact name @ agent" strings, e.g. ["predicate=value@planner"]',
        "set", "fact_by", [f"{x}@{by[x]}" for x in d_jwt["fact_labels"]], "decision_fact_agents", decision=d_jwt["label"],
    )  # fmt: skip
    src_of = {f["label"]: f["source_uri"] for f in led.facts}
    add(
        "decision_provenance",
        f'Which source documents (uris) back the facts that the decision "{d_jwt["text"]}" relied on?',
        "a JSON list of source uris",
        "set", "source", _dedupe(src_of[x] for x in d_jwt["fact_labels"]), "decision_sources", decision=d_jwt["label"],
    )  # fmt: skip
    assert d_pg["agent"] == "builder"


def _handoffs(b: _Builder) -> None:
    led, add, fmt_facts, superseded = b.led, b.add, b.fmt_facts, b.superseded
    h3, h7 = led.handoff("t03-design-endpoints"), led.handoff("t07-implement-crud-spec")
    add(
        "handoffs", "What artifacts (uris) did the handoff for task t03-design-endpoints carry?",
        "a JSON list of artifact uris", "set", "artifact", h3["artifacts"], "handoff_artifacts", task=h3["task_id"],
    )  # fmt: skip
    add(
        "handoffs", "Who handed task t03-design-endpoints over, and to whom?",
        'a JSON list with one string "sender->receiver"', "set", "text", [f"{h3['from']}->{h3['to']}"],
        "handoff_route", task=h3["task_id"],
    )  # fmt: skip
    add(
        "handoffs", "Which facts did the handoff for task t07-implement-crud-spec carry?",
        fmt_facts, "set", "fact", h7["fact_labels"], "handoff_facts", task=h7["task_id"],
    )  # fmt: skip
    add(
        "handoffs", "For which tasks did the planner receive a handoff?",
        "a JSON list of task ids", "set", "task", [h["task_id"] for h in led.handoffs if h["to"] == "planner"],
        "handoffs_to", agent="planner",
    )  # fmt: skip
    add(
        "handoffs", "Which handoffs carried a fact that has since been superseded? Name the task of each handoff.",
        "a JSON list of task ids", "set", "task",
        [h["task_id"] for h in led.handoffs if superseded & set(h["fact_labels"])], "handoffs_with_superseded_facts",
    )  # fmt: skip


def _time_travel(b: _Builder) -> None:
    led, add, subj, fmt_facts, v1, v2 = b.led, b.add, b.subj, b.fmt_facts, b.v1, b.v2
    marks = led.marks
    for mark, pred, what in (
        ("after_v1", "api_version", "just after it was first asserted and before anything newer"),
        ("after_v2", "api_version", "just after the new style guide was ingested"),
    ):
        t = marks[mark]
        add(
            "time_travel",
            f"What value of the fact `{pred}` of subject '{subj}' (global scope) was valid at t={t} ({what})?",
            "a JSON list with the valid value(s), e.g. [\"v1\"]", "set", "value",
            [f["value"] for f in _facts_at(led, subj, pred, t)], "as_of_values", subject=subj, predicate=pred, t=t,
        )  # fmt: skip
    for mark, what in (
        ("after_jwt", "after only the security note had been ingested"),
        ("after_apikey", "after both sides were asserted"),
    ):
        t = marks[mark]
        add(
            "time_travel",
            f"Which `auth_method` facts of subject '{subj}' (global scope) were valid at t={t} ({what})?",
            fmt_facts, "set", "fact", [f["label"] for f in _facts_at(led, subj, "auth_method", t)], "as_of_facts",
            subject=subj, predicate="auth_method", t=t,
        )  # fmt: skip
    add(
        "time_travel", f"List every value that `api_version` of subject '{subj}' has had, oldest first.",
        "a JSON list of values, oldest first", "ordered", "value", [v1["value"], v2["value"]], "value_history",
        subject=subj, predicate="api_version",
    )  # fmt: skip


def _supersession(b: _Builder) -> None:
    led, add, v1, v2, superseded = b.led, b.add, b.v1, b.v2, b.superseded
    add(
        "supersession", "Which decisions were based on a fact that was later superseded?",
        "a JSON list of decision names", "set", "decision", _decisions_on(led, superseded), "decisions_on_superseded",
    )  # fmt: skip
    add(
        "supersession", "Which fact superseded `api_version=v1`, and which agent asserted it?",
        'a JSON list with one string "fact name @ agent"', "set", "fact_by", [f"{v2['label']}@{v2['agent']}"],
        "superseder", fact=v1["label"],
    )  # fmt: skip
    add(
        "supersession", "Which agent asserted the fact `api_version=v1` that was later superseded?",
        "one agent id", "value", "agent", v1["agent"], "fact_agent", fact=v1["label"],
    )  # fmt: skip
    add(
        "supersession", "Which decisions are based on the current `api_version` fact?",
        "a JSON list of decision names", "set", "decision", _decisions_on(led, {v2["label"]}),
        "decisions_on_fact", fact=v2["label"],
    )  # fmt: skip


def _dependencies(b: _Builder) -> None:
    led, add = b.led, b.add
    for tid in ("t03-design-endpoints", "t06-write-db-schema", "t09-review-spec"):
        add(
            "dependencies", f"Which tasks are blocked (directly or transitively) if {tid} fails?",
            "a JSON list of task ids", "set", "task", _downstream(led, tid), "blocked_by_failure", task=tid,
        )  # fmt: skip
    deps7 = next(t for t in led.tasks if t["id"] == "t07-implement-crud-spec")["depends_on"]
    add(
        "dependencies", "Which tasks does t07-implement-crud-spec directly depend on?",
        "a JSON list of task ids", "set", "task", deps7, "direct_dependencies", task="t07-implement-crud-spec",
    )  # fmt: skip
    add(
        "dependencies",
        "Considering only the dependency graph, which tasks become ready as soon as t01-gather-requirements is done (all of their dependencies are done, and they are not t01 itself)?",
        "a JSON list of task ids", "set", "task",
        [t["id"] for t in led.tasks if t["depends_on"] and set(t["depends_on"]) <= {"t01-gather-requirements"}],
        "ready_after", done=["t01-gather-requirements"],
    )  # fmt: skip


def _contradictions(b: _Builder) -> None:
    add, fmt_facts, jwt, key, mongo, pg = b.add, b.fmt_facts, b.jwt, b.key, b.mongo, b.pg
    add(
        "contradictions", "Which current facts conflict with each other (same subject and predicate, different values)?",
        fmt_facts, "set", "fact", [jwt["label"], key["label"]], "active_conflicts",
    )  # fmt: skip
    add(
        "contradictions", "For each side of the current conflict, which agent asserted it?",
        'a JSON list of "fact name @ agent" strings', "set", "fact_by", [f"{jwt['label']}@{jwt['agent']}", f"{key['label']}@{key['agent']}"],
        "active_conflict_agents",
    )  # fmt: skip
    add(
        "contradictions", "Which source document backs the API-key side of the conflict?",
        "one source uri", "value", "source", key["source_uri"], "fact_source", fact=key["label"],
    )  # fmt: skip
    assert mongo["contradicts"] == [pg["label"]]


def _recovery(b: _Builder) -> None:
    led, add = b.led, b.add
    reclaimed = [c for c in led.claims if c["reclaimed_from"]]
    add(
        "recovery", "Which tasks were reclaimed after the agent holding them stopped (its lease expired)?",
        "a JSON list of task ids", "set", "task", [c["task_id"] for c in reclaimed], "reclaimed_tasks",
    )  # fmt: skip
    add(
        "recovery", "Which agent took over t03-design-endpoints after the first claimer died?",
        "one agent id", "value", "agent", reclaimed[0]["agent"], "reclaimer", task="t03-design-endpoints",
    )  # fmt: skip
    add(
        "recovery", "Which agent held the expired lease on t03-design-endpoints (the one that died)?",
        "one agent id", "value", "agent", reclaimed[0]["reclaimed_from"], "previous_claimer", task="t03-design-endpoints",
    )  # fmt: skip
    add(
        "recovery", "Which tasks did the builder complete?",
        "a JSON list of task ids", "set", "task", [c["task_id"] for c in led.completions if c["agent"] == "builder"],
        "completed_by", agent="builder",
    )  # fmt: skip


def _memory_scope(b: _Builder) -> None:
    led, add, subj, fmt_facts, v2, pg = b.led, b.add, b.subj, b.fmt_facts, b.v2, b.pg
    superseded, forgotten = b.superseded, b.forgotten
    add(
        "memory_scope", f"What is the current value of `api_version` for '{subj}'?",
        "one value", "value", "value", v2["value"], "current_value", subject=subj, predicate="api_version",
    )  # fmt: skip
    add(
        "memory_scope", f"What is the current value of `database` for '{subj}'?",
        "one value", "value", "value", pg["value"], "current_value", subject=subj, predicate="database",
    )  # fmt: skip
    current = [
        f["label"] for f in led.facts if f["label"] not in superseded and f["label"] not in forgotten
        and f["scope"] in ("global", ACME_SCOPE)
    ]  # fmt: skip
    add(
        "memory_scope", f"Which current facts are visible from the scope {ACME_SCOPE} (that scope's own facts plus global ones)?",
        fmt_facts, "set", "fact", current, "visible_facts", scope=ACME_SCOPE,
    )  # fmt: skip
    add(
        "memory_scope", f"Does any fact of the scope {BILLING_SCOPE} (subject '{BILLING_SUBJECT}') appear among the facts visible from {ACME_SCOPE}?",
        "yes or no", "yesno", "value", "no", "scope_leak", scope=ACME_SCOPE, other=BILLING_SCOPE,
    )  # fmt: skip
    bill = next(f for f in led.facts if f["scope"] == BILLING_SCOPE)
    add(
        "memory_scope", f"In which scope is the fact `{bill['label']}` of subject '{BILLING_SUBJECT}'?",
        "one scope name such as global or project:<name>", "value", "scope", bill["scope"], "fact_scope", fact=bill["label"],
    )  # fmt: skip


def _episodes(b: _Builder) -> None:
    led, add = b.led, b.add
    ep_v1 = next(e for e in led.episodes if "v1 is withdrawn" in e["text"])
    ep_pg = next(e for e in led.episodes if "PostgreSQL 16" in e["text"])
    add(
        "episodes", "Which agent recorded the episode saying that API version v1 is withdrawn?",
        "one agent id", "value", "agent", ep_v1["agent"], "episode_agent", contains="v1 is withdrawn",
    )  # fmt: skip
    add(
        "episodes", "Which agent recorded the episode about the notes, tags and note_tags tables?",
        "one agent id", "value", "agent", ep_pg["agent"], "episode_agent", contains="note_tags",
    )  # fmt: skip
    add(
        "episodes", "How many episodes did the builder record in total (across all of its sessions)?",
        "an integer", "int", "value", sum(e["agent"] == "builder" for e in led.episodes), "episode_count", agent="builder",
    )  # fmt: skip


def _forgetting(b: _Builder) -> None:
    led, add, fmt_facts, forgotten = b.led, b.add, b.fmt_facts, b.forgotten
    src_forum = led.forgotten[0]["source_uri"]
    add(
        "forgetting", f"After forgetting the source {src_forum}, which facts derived from it are still current?",
        fmt_facts + " (an empty list if none)", "set", "fact", [], "remaining_from_source", source=src_forum,
    )  # fmt: skip
    add(
        "forgetting", f"Which facts were forgotten when the source {src_forum} was forgotten?",
        fmt_facts, "set", "fact", forgotten, "forgotten_facts", source=src_forum,
    )  # fmt: skip
    add(
        "forgetting", "Which decisions were based on a fact that was later forgotten?",
        "a JSON list of decision names", "set", "decision", _decisions_on(led, set(forgotten)),
        "decisions_on_forgotten",
    )  # fmt: skip


def build_questions(led: Ledger) -> list[Question]:
    b = _Builder(led)
    for family in (
        _decision_provenance,
        _handoffs,
        _time_travel,
        _supersession,
        _dependencies,
        _contradictions,
        _recovery,
        _memory_scope,
        _episodes,
        _forgetting,
    ):
        family(b)
    return b.qs


# ------------------------------------------------------------------------------------------------ files
def dump_questions(qs: list[Question], led: Ledger, path: Path) -> None:
    """Write ``questions.yaml`` (JSON-compatible YAML so that it round-trips through either loader)."""
    import yaml

    doc = {
        "schema": "crucible-l2-questions/1",
        "generated_from": "plexus.crucible.l2.scenario.play (the Acme Notes script); answers are derived, never typed",
        "scenario": scenario_summary(led),
        "conventions": CONVENTIONS,
        "questions": [q.to_json() for q in qs],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8", newline="\n"
    )


def load_questions(path: Path) -> list[Question]:
    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Question.from_json(d) for d in doc["questions"]]


def scenario_summary(led: Ledger) -> dict[str, Any]:
    return {
        "subject": led.subject,
        "agents": led.agents,
        "tasks": len(led.tasks),
        "decisions": len(led.decisions),
        "handoffs": len(led.handoffs),
        "facts": len(led.facts),
        "episodes": len(led.episodes),
        "sources": len(led.sources),
        "supersedes": sum(len(f["superseded"]) for f in led.facts),
        "conflicting_pairs": sum(1 for f in led.facts if f["contradicts"]),
        "reclaims": sum(1 for c in led.claims if c["reclaimed_from"]),
        "forgotten_facts": sum(len(x["fact_labels"]) for x in led.forgotten),
        "marks": led.marks,
    }


def generate(root: str | Path) -> tuple[Ledger, list[Question]]:
    """Play the script on a throw-away B1 store under ``root`` and derive the questions from the ledger.

    The ledger is arm-independent (the tests check that all arms produce the same one), so any arm would do;
    B1 needs neither a database server nor an embedding model.
    """
    from plexus.crucible.api import BackendSpec
    from plexus.crucible.backends import open_backend
    from plexus.crucible.l2.scenario import play

    b = open_backend(BackendSpec(arm="B1", tenant="l2_truth", root=str(root)))
    try:
        led = play(b)
    finally:
        b.close()
    return led, build_questions(led)
