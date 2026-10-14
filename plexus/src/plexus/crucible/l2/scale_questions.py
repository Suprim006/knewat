"""The L2-at-scale question set: 40 exact-match questions (10 families x 4) about single sprints of a 20-sprint history.

Every question names the sprint it is about (``In sprint S07: ...``), so a retrieval query built from the question text
can find that sprint's records, and so the answer is well defined in a history where the same story repeats 20 times.
Answers are derived from the per-sprint ledger (never typed). The sprint of each question is chosen by a pre-registered
rule (:func:`assign_sprints`): early / middle / late thirds in rotation, round-robin over a seeded shuffle of each third.

The scoring rule, normalisation and reply parsing are those of ``questions.py`` (imported, not copied).
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from plexus.crucible.l2.questions import (
    FAMILIES,
    Question,
    _decisions_on,
    _dedupe,
    _downstream,
    _facts_at,
)
from plexus.crucible.l2.scale_scenario import ScaleLedger, Sprint
from plexus.crucible.l2.scenario import Ledger, decision_label

SEED = 20261015
FMT_FACTS = 'a JSON list of fact names, e.g. ["predicate=value"]'
CONVENTIONS_SCALE_EXTRA = (
    "- The history contains many independent sprints S01, S02, ... (the team ran the same kind of project again and\n"
    "  again). Every question is about ONE sprint and names it; ignore records of the other sprints. A sprint's task ids\n"
    "  start with its lower-case tag (for example `s07-t03-design-endpoints`), its decisions start with its tag, and its\n"
    "  subjects, source uris, artifacts and scopes carry it."
)

Spec = tuple[
    str, str, str, str, str, Any, str, dict[str, Any]
]  # family, text, format, kind, item, answer, op, args


def _only(xs: list[Any], what: str) -> Any:
    if len(xs) != 1:
        raise KeyError(f"{len(xs)} matches for {what}")
    return xs[0]


def sprint_specs(sp: Sprint, led: Ledger) -> list[Spec]:
    """The 40 question slots for one sprint, in family order (4 per family)."""
    pre = f"In sprint {sp.tag}: "
    subj = sp.subject
    out: list[Spec] = []

    def add(
        family: str, text: str, fmt: str, kind: str, item: str, answer: Any, op: str, **args: Any
    ) -> None:
        out.append((family, pre + text, fmt, kind, item, answer, op, {**args, "sprint": sp.low}))

    v_old, v_new = led.fact(f"api_version={sp.v_old}"), led.fact(f"api_version={sp.v_new}")
    jwt, key = led.fact(f"auth_method={sp.jwt}"), led.fact(f"auth_method={sp.apikey}")
    poison, db = led.fact(f"database={sp.poison}"), led.fact(f"database={sp.db}")
    assert poison["contradicts"] == [db["label"]]
    superseded = {f["label"] for f in led.facts if any(f["label"] in g["superseded"] for g in led.facts)}
    forgotten = _dedupe(x for fg in led.forgotten for x in fg["fact_labels"])
    src_forum = led.forgotten[0]["source_uri"]
    d_jwt, d_poison = led.decision(decision_label(sp.d_jwt)), led.decision(decision_label(sp.d_poison))
    by = {f["label"]: f["agent"] for f in led.facts}
    src_of = {f["label"]: f["source_uri"] for f in led.facts}
    h3 = led.handoff(sp.tid("t03-design-endpoints"))
    h7 = led.handoff(sp.tid("t07-implement-crud-spec"))
    marks = led.marks
    reclaimed = [c for c in led.claims if c["reclaimed_from"]]
    t3 = sp.tid("t03-design-endpoints")

    # ---- decision provenance
    fam = "decision_provenance"
    add(fam, f'Which facts was the decision "{d_jwt["text"]}" based on?', FMT_FACTS, "set", "fact",
        d_jwt["fact_labels"], "decision_facts", decision=d_jwt["label"])  # fmt: skip
    add(fam, f'Which facts was the decision "{d_poison["text"]}" based on?', FMT_FACTS, "set", "fact",
        d_poison["fact_labels"], "decision_facts", decision=d_poison["label"])  # fmt: skip
    add(fam, f'For each fact that the decision "{d_jwt["text"]}" was based on, which agent asserted it?',
        'a JSON list of "fact name @ agent" strings, e.g. ["predicate=value@planner"]', "set", "fact_by",
        [f"{x}@{by[x]}" for x in d_jwt["fact_labels"]], "decision_fact_agents", decision=d_jwt["label"])  # fmt: skip
    add(fam, f'Which source documents (uris) back the facts that the decision "{d_jwt["text"]}" relied on?',
        "a JSON list of source uris", "set", "source", _dedupe(src_of[x] for x in d_jwt["fact_labels"]),
        "decision_sources", decision=d_jwt["label"])  # fmt: skip

    # ---- handoffs
    fam = "handoffs"
    add(fam, f"What artifacts (uris) did the handoff for task {t3} carry?", "a JSON list of artifact uris", "set",
        "artifact", h3["artifacts"], "handoff_artifacts", task=t3)  # fmt: skip
    add(fam, f"Which facts did the handoff for task {h7['task_id']} carry?", FMT_FACTS, "set", "fact",
        h7["fact_labels"], "handoff_facts", task=h7["task_id"])  # fmt: skip
    add(fam, "For which tasks did the planner receive a handoff?", "a JSON list of task ids", "set", "task",
        [h["task_id"] for h in led.handoffs if h["to"] == "planner"], "handoffs_to", agent="planner")  # fmt: skip
    add(fam, "Which handoffs carried a fact that has since been superseded? Name the task of each handoff.",
        "a JSON list of task ids", "set", "task",
        [h["task_id"] for h in led.handoffs if superseded & set(h["fact_labels"])],
        "handoffs_with_superseded_facts")  # fmt: skip

    # ---- time travel
    fam = "time_travel"
    t = marks["after_v1"]
    add(fam, f"What value of the fact `api_version` of subject '{subj}' (global scope) was valid at t={t} "
        "(just after it was first asserted and before anything newer)?",
        f'a JSON list with the valid value(s), e.g. ["{sp.v_old}"]', "set", "value",
        [f["value"] for f in _facts_at(led, subj, "api_version", t)], "as_of_values",
        subject=subj, predicate="api_version", t=t)  # fmt: skip
    for mark, what in (("after_jwt", "after only the security note had been ingested"),
                       ("after_apikey", "after both sides were asserted")):  # fmt: skip
        t = marks[mark]
        add(fam, f"Which `auth_method` facts of subject '{subj}' (global scope) were valid at t={t} ({what})?",
            FMT_FACTS, "set", "fact", [f["label"] for f in _facts_at(led, subj, "auth_method", t)], "as_of_facts",
            subject=subj, predicate="auth_method", t=t)  # fmt: skip
    add(fam, f"List every value that `api_version` of subject '{subj}' has had, oldest first.",
        "a JSON list of values, oldest first", "ordered", "value", [v_old["value"], v_new["value"]],
        "value_history", subject=subj, predicate="api_version")  # fmt: skip

    # ---- supersession impact
    fam = "supersession"
    add(fam, "Which decisions were based on a fact that was later superseded?", "a JSON list of decision names",
        "set", "decision", _decisions_on(led, superseded), "decisions_on_superseded")  # fmt: skip
    add(fam, f"Which fact superseded `{v_old['label']}`, and which agent asserted it?",
        'a JSON list with one string "fact name @ agent"', "set", "fact_by", [f"{v_new['label']}@{v_new['agent']}"],
        "superseder", fact=v_old["label"])  # fmt: skip
    add(fam, f"Which agent asserted the fact `{v_old['label']}` that was later superseded?", "one agent id",
        "value", "agent", v_old["agent"], "fact_agent", fact=v_old["label"])  # fmt: skip
    add(fam, f"Which decisions are based on the current `api_version` fact of '{subj}'?",
        "a JSON list of decision names", "set", "decision", _decisions_on(led, {v_new["label"]}),
        "decisions_on_fact", fact=v_new["label"])  # fmt: skip

    # ---- dependencies
    fam = "dependencies"
    for name in ("t03-design-endpoints", "t09-review-spec"):
        tid = sp.tid(name)
        add(fam, f"Which tasks are blocked (directly or transitively) if {tid} fails?", "a JSON list of task ids",
            "set", "task", _downstream(led, tid), "blocked_by_failure", task=tid)  # fmt: skip
    t7 = sp.tid("t07-implement-crud-spec")
    add(fam, f"Which tasks does {t7} directly depend on?", "a JSON list of task ids", "set", "task",
        next(x for x in led.tasks if x["id"] == t7)["depends_on"], "direct_dependencies", task=t7)  # fmt: skip
    t1 = sp.tid("t01-gather-requirements")
    add(fam, f"Considering only the dependency graph, which tasks become ready as soon as {t1} is done "
        "(all of their dependencies are done, and they are not that task itself)?", "a JSON list of task ids",
        "set", "task", [x["id"] for x in led.tasks if x["depends_on"] and set(x["depends_on"]) <= {t1}],
        "ready_after", done=[t1])  # fmt: skip

    # ---- contradictions
    fam = "contradictions"
    add(fam, "Which current facts conflict with each other (same subject and predicate, different values)?",
        FMT_FACTS, "set", "fact", [jwt["label"], key["label"]], "active_conflicts")  # fmt: skip
    add(fam, "For each side of the current conflict, which agent asserted it?",
        'a JSON list of "fact name @ agent" strings', "set", "fact_by",
        [f"{jwt['label']}@{jwt['agent']}", f"{key['label']}@{key['agent']}"], "active_conflict_agents")  # fmt: skip
    add(fam, "Which source document backs the API-key side of the conflict?", "one source uri", "value", "source",
        key["source_uri"], "fact_source", fact=key["label"])  # fmt: skip
    add(fam, f"Which agent asserted the fact `{jwt['label']}`?", "one agent id", "value", "agent", jwt["agent"],
        "fact_agent", fact=jwt["label"])  # fmt: skip

    # ---- recovery
    fam = "recovery"
    add(fam, "Which tasks were reclaimed after the agent holding them stopped (its lease expired)?",
        "a JSON list of task ids", "set", "task", [c["task_id"] for c in reclaimed], "reclaimed_tasks")  # fmt: skip
    add(fam, f"Which agent took over {t3} after the first claimer died?", "one agent id", "value", "agent",
        reclaimed[0]["agent"], "reclaimer", task=t3)  # fmt: skip
    add(fam, f"Which agent held the expired lease on {t3} (the one that died)?", "one agent id", "value", "agent",
        reclaimed[0]["reclaimed_from"], "previous_claimer", task=t3)  # fmt: skip
    add(fam, "Which tasks did the builder complete?", "a JSON list of task ids", "set", "task",
        [c["task_id"] for c in led.completions if c["agent"] == "builder"], "completed_by", agent="builder")  # fmt: skip

    # ---- memory currency and scope
    fam = "memory_scope"
    add(fam, f"What is the current value of `api_version` for '{subj}'?", "one value", "value", "value",
        v_new["value"], "current_value", subject=subj, predicate="api_version")  # fmt: skip
    visible = [f["label"] for f in led.facts if f["label"] not in superseded and f["label"] not in forgotten
               and f["subject"] == subj and f["scope"] in ("global", sp.acme_scope)]  # fmt: skip
    add(fam, f"Which current facts about '{subj}' are visible from the scope {sp.acme_scope} "
        "(that scope's own facts plus global ones)?", FMT_FACTS, "set", "fact", visible, "visible_facts",
        scope=sp.acme_scope, subject=subj)  # fmt: skip
    add(fam, f"Does any fact of the scope {sp.billing_scope} (subject '{sp.billing_subject}') appear among the "
        f"facts visible from {sp.acme_scope}?", "yes or no", "yesno", "value", "no", "scope_leak",
        scope=sp.acme_scope, other=sp.billing_scope)  # fmt: skip
    bill = _only([f for f in led.facts if f["scope"] == sp.billing_scope], "billing fact")
    add(fam, f"In which scope is the fact `{bill['label']}` of subject '{sp.billing_subject}'?",
        "one scope name such as global or project:<name>", "value", "scope", bill["scope"], "fact_scope",
        fact=bill["label"])  # fmt: skip

    # ---- cross-session recall (episodes)
    fam = "episodes"

    def ep(substr: str) -> dict[str, Any]:
        return _only([e for e in led.episodes if substr in e["text"]], f"episode {substr!r}")

    e1, e2, e3 = ep(f"{sp.tag}: Style guide"), ep(f"{sp.tag}: Schema:"), ep(f"{sp.tag}: Took over")
    add(fam, f"Which agent recorded the episode saying that API version {sp.v_old} is withdrawn?", "one agent id",
        "value", "agent", e1["agent"], "episode_agent", contains=f"{sp.tag}: Style guide")  # fmt: skip
    add(fam, "Which agent recorded the episode about the notes, tags and note_tags tables?", "one agent id",
        "value", "agent", e2["agent"], "episode_agent", contains=f"{sp.tag}: Schema:")  # fmt: skip
    add(fam, "How many episodes did the builder record in total (across all of its sessions)?", "an integer", "int",
        "value", sum(e["agent"] == "builder" for e in led.episodes), "episode_count", agent="builder")  # fmt: skip
    add(fam, f"Which agent recorded the episode about taking over {t3} after the previous owner's lease expired?",
        "one agent id", "value", "agent", e3["agent"], "episode_agent", contains=f"{sp.tag}: Took over")  # fmt: skip

    # ---- forgetting
    fam = "forgetting"
    add(fam, f"After forgetting the source {src_forum}, which facts derived from it are still current?",
        FMT_FACTS + " (an empty list if none)", "set", "fact", [], "remaining_from_source", source=src_forum)  # fmt: skip
    add(fam, f"Which facts were forgotten when the source {src_forum} was forgotten?", FMT_FACTS, "set", "fact",
        forgotten, "forgotten_facts", source=src_forum)  # fmt: skip
    add(fam, "Which decisions were based on a fact that was later forgotten?", "a JSON list of decision names",
        "set", "decision", _decisions_on(led, set(forgotten)), "decisions_on_forgotten")  # fmt: skip
    add(fam, f"Which agent asserted the fact `{poison['label']}` that was later forgotten?", "one agent id",
        "value", "agent", poison["agent"], "fact_agent", fact=poison["label"])  # fmt: skip
    return out


def assign_sprints(k: int, n_questions: int, seed: int = SEED) -> list[int]:
    """The pre-registered rule: question ``i`` (family order) takes stratum ``i % 3`` (early, middle, late third of the
    k sprints); inside a stratum sprints are dealt round-robin from a seeded shuffle, so every sprint of a stratum is
    used before any is used twice."""
    n = k // 3
    strata = [list(range(1, n + 1)), list(range(n + 1, k - n + 1)), list(range(k - n + 1, k + 1))]
    rng = random.Random(seed)
    for s in strata:
        rng.shuffle(s)
    used = [0, 0, 0]
    out = []
    for i in range(n_questions):
        s = i % 3
        out.append(strata[s][used[s] % len(strata[s])])
        used[s] += 1
    return out


def build_scale_questions(sl: ScaleLedger, seed: int = SEED) -> list[Question]:
    per_sprint = [sprint_specs(sp, led) for sp, led in zip(sl.sprints, sl.ledgers, strict=True)]
    n_slots = len(per_sprint[0])
    chosen = assign_sprints(len(sl.sprints), n_slots, seed)
    qs = []
    for i, n in enumerate(chosen):
        family, text, fmt, kind, item, answer, op, args = per_sprint[n - 1][i]
        qs.append(Question(f"Q{i + 1:02d}", family, text, fmt, kind, item, answer, op, args))
    assert {q.family for q in qs} == set(FAMILIES)
    return qs


def scale_summary(sl: ScaleLedger, qs: list[Question]) -> dict[str, Any]:
    return {
        **sl.summary(),
        "question_sprints": {q.id: q.args["sprint"] for q in qs},
    }


def dump_scale_questions(qs: list[Question], sl: ScaleLedger, path: Path) -> None:
    import yaml

    doc = {
        "schema": "crucible-l2-scale-questions/1",
        "generated_from": "plexus.crucible.l2.scale_scenario.play_scale (K sprints); answers are derived from the per-sprint ledgers, never typed",
        "seed": SEED,
        "scenario": scale_summary(sl, qs),
        "questions": [q.to_json() for q in qs],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8", newline="\n"
    )


def load_scale_questions(path: Path) -> list[Question]:
    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Question.from_json(d) for d in doc["questions"]]


def generate_scale(root: str | Path, k: int) -> tuple[ScaleLedger, list[Question]]:
    """Play k sprints on a throw-away B1 store and derive the questions from the ledgers."""
    from plexus.crucible.api import BackendSpec
    from plexus.crucible.backends import open_backend
    from plexus.crucible.l2.scale_scenario import play_scale

    b = open_backend(BackendSpec(arm="B1", tenant="l2s_truth", root=str(root)))
    try:
        sl = play_scale(b, k)
    finally:
        b.close()
    return sl, build_scale_questions(sl)
