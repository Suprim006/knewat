"""The L8 live sprint S21: 16 tasks (15 at kickoff + t12 mid-run), two specials, needs, artifacts, briefs (``l8-v1``).

Every task names the code settings it ``needs`` (``module.function``; their values are sentinel tokens) and the
artifact file it must write (``artifacts/<task>/<file>``). A task's artifact is *correct* when it contains the token
each needed function returns at the time of the action. Briefs come in two renderings of the same instructions:
``mcp`` (the Plexus tool names; arms P and B1) and ``files`` (arm B0', Claude Code with its own memory files). The
content of each instruction is the same; only the verb that stores or reads team memory differs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plexus.crucible.l2.scale_scenario import Sprint
from plexus.demo.scenario import load_scenario

PROMPT_VERSION = "l8-v1"
SUBJECT = "Acme Notes API S21"
ROLES = ("planner", "researcher", "builder")

# long-horizon facts from the 20-sprint history (ground truth: the L2-scale generator's own values)
S07, S13, S20 = Sprint(7), Sprint(13), Sprint(20)
HISTORY_NEEDS: dict[str, dict[str, list[str]]] = {
    # task -> label -> strings that must ALL appear in the artifact
    "t13-reuse-billing-cycle": {
        "S07 billing cycle": [S07.cycle],
        "S13 API-key header": [S13.apikey.split(" in ", 1)[1].split()[0]],  # 'X-Core-Key'
    },
    "t16-release-notes": {"S20 release channel": [S20.channel]},
}


@dataclass(frozen=True)
class L8Task:
    id: str
    title: str
    role: str
    priority: int
    depends_on: tuple[str, ...]
    needs: tuple[str, ...]  # 'module.function'
    records: tuple[str, ...]  # settings the brief asks to store as team facts
    artifact: str  # file name under artifacts/<id>/
    docs: tuple[str, ...] = ()  # acme source stems shown in the prompt
    extra_docs: tuple[str, ...] = ()  # L8 documents (X2)
    mid_run: bool = False
    mcp: str = ""
    files: str = ""

    @property
    def artifact_path(self) -> str:
        return f"artifacts/{self.id}/{self.artifact}"

    def spec(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "depends_on": list(self.depends_on),
        }


@dataclass(frozen=True)
class L8Special:
    name: str
    role: str
    docs: tuple[str, ...]
    mcp: str
    files: str


def _needs_line(t_needs: tuple[str, ...]) -> str:
    return ", ".join(f"`{n}`" for n in t_needs)


ARTIFACT_RULE = (
    "Write the artifact file `{path}` (Markdown) with the Write tool. It must state the value of each of these code "
    "settings, one per line in the form `module.function: VALUE`: {needs}."
)
RECORD_MCP = (
    "Read the listed functions in the repository and store each value as a team fact: assert_fact with subject "
    f"'{SUBJECT}', predicate '<module>.<function>' (e.g. 'api.base_path') and value = the token it returns. "
    "Settings to record: {records}."
)
RECORD_FILES = (
    "Read the listed functions in the repository and store each value in team memory: one line "
    "`<module>.<function> = VALUE` per setting in `memory/facts.md`. Settings to record: {records}."
)
DONE_MCP = (
    "Then complete the task (complete_task) with one artifact: kind 'file', uri '{path}', and a one-line summary "
    "that names the values you wrote."
)
DONE_FILES = "Then record in `memory/tasks.md` that task {id} is done, with a one-line summary that names the values you wrote."


def _t(
    id: str, title: str, role: str, prio: int, deps: tuple[str, ...], needs: tuple[str, ...], art: str, *,
    records: tuple[str, ...] = (), docs: tuple[str, ...] = (), extra_docs: tuple[str, ...] = (),
    mid_run: bool = False, mcp: str = "", files: str = "",
) -> L8Task:  # fmt: skip
    path = f"artifacts/{id}/{art}"
    parts_m, parts_f = [mcp.strip()] if mcp else [], [files.strip()] if files else []
    if records:
        parts_m.append(RECORD_MCP.format(records=_needs_line(records)))
        parts_f.append(RECORD_FILES.format(records=_needs_line(records)))
    rule = ARTIFACT_RULE.format(path=path, needs=_needs_line(needs))
    parts_m += [rule, DONE_MCP.format(path=path)]
    parts_f += [rule, DONE_FILES.format(id=id)]
    return L8Task(
        id, title, role, prio, deps, needs, records, art, docs, extra_docs, mid_run,
        "\n".join(parts_m), "\n".join(parts_f),
    )  # fmt: skip


API5 = tuple(f"api.{f}" for f in ("base_path", "page_size", "max_body", "cors_origin", "error_format"))
DB5 = tuple(f"db.{f}" for f in ("engine", "pool_size", "schema_name", "replica_count", "backup_window"))
AUTH5 = tuple(f"auth.{f}" for f in ("token_ttl", "hash_rounds", "session_cookie", "mfa_window", "key_header"))
NOTES5 = tuple(f"notes.{f}" for f in ("max_length", "tag_limit", "archive_days", "share_mode", "title_max"))
RL5 = tuple(f"ratelimit.{f}" for f in ("window", "burst", "per_user", "per_key", "retry_after"))
REL5 = tuple(
    f"release.{f}" for f in ("channel", "version_tag", "rollout_pct", "freeze_day", "changelog_path")
)
T09_NEEDS = ("api.base_path", "auth.token_ttl", "db.engine")
T13_NEEDS = ("billing.cycle", "billing.currency")
T15_NEEDS = (
    "config.region", "config.secret_store", "config.env_name", "db.pool_size", "db.replica_count",
    "auth.hash_rounds", "auth.mfa_window", "ratelimit.window",
)  # fmt: skip
T16_NEEDS = tuple(dict.fromkeys(T09_NEEDS + T13_NEEDS + T15_NEEDS))

TASKS: tuple[L8Task, ...] = (
    _t(
        "t01-gather-requirements",
        "Gather requirements",
        "researcher",
        50,
        (),
        API5,
        "requirements.md",
        records=API5,
        docs=("01_product_brief", "02_api_style_guide_v1"),
        mcp=f"Register the two documents below with add_source (title = the document's heading, uri = "
        f"'acme-docs/<file name>', text = the full document). Assert two facts about subject '{SUBJECT}', each with "
        "the source_id of its document: predicate 'purpose' (one short sentence, from the product brief) and "
        "predicate 'api_version' (the short version label the style guide prescribes, e.g. 'v1').",
        files="Read the two documents below. Record in `memory/facts.md` the product's purpose (one short sentence) "
        "and the api_version the style guide prescribes (e.g. 'v1'), each with the document it came from.",
    ),
    _t(
        "t02-choose-api-version",
        "Choose the API version",
        "planner",
        45,
        ("t01-gather-requirements",),
        ("api.base_path", "api.error_format"),
        "decision.md",
        mcp="Recall 'API version' and the api settings the team recorded. Record ONE decision (record_decision) saying "
        "which API version and base path the team builds against, with based_on_fact_ids = the fact ids you relied on.",
        files="Read the team memory for the API version and the api settings the team recorded. Record ONE decision in "
        "`memory/decisions.md` saying which API version and base path the team builds against, and which "
        "recorded facts it relies on.",
    ),
    _t(
        "t03-design-endpoints",
        "Design the endpoints",
        "builder",
        40,
        ("t02-choose-api-version",),
        ("api.base_path", "api.page_size", "api.max_body"),
        "openapi-draft.md",
        mcp="Recall 'API version'. Write a short episode (remember_episode) naming the endpoints you will draft "
        "(list/create/read/update/delete notes under the base path). After completing, hand off to 'planner' "
        "(handoff) with a short note, the artifact_id and the fact ids you relied on.",
        files="Read the team memory for the API version. Add a short note to `memory/log.md` naming the endpoints you "
        "will draft (list/create/read/update/delete notes under the base path). After that, leave a handoff "
        "note for 'planner' in `memory/handoffs.md` naming the artifact and the facts you relied on.",
    ),
    _t(
        "t04-survey-infra-security",
        "Survey infrastructure and security",
        "researcher",
        35,
        ("t01-gather-requirements",),
        DB5 + AUTH5,
        "constraints.md",
        records=DB5 + AUTH5,
        docs=("03_infra_note", "04_security_note"),
        mcp=f"Register the two documents below with add_source (uri = 'acme-docs/<file name>'). Assert two facts about "
        f"subject '{SUBJECT}', each with its source_id: predicate 'database' (the database product and version) "
        "and predicate 'auth_method' (the authentication scheme the security note requires).",
        files="Read the two documents below. Record in `memory/facts.md` the database (product and version) and the "
        "auth_method the security note requires, each with the document it came from.",
    ),
    _t(
        "t05-choose-auth",
        "Choose the authentication scheme",
        "planner",
        30,
        ("t04-survey-infra-security",),
        ("auth.token_ttl", "auth.key_header"),
        "auth-decision.md",
        docs=("05_customer_request",),
        mcp="Recall 'authentication' to see what is already known. Register the customer request below with "
        f"add_source (kind 'chat', uri 'acme-docs/<file name>'). The customer asks for something different from "
        f"the security note: assert predicate 'auth_method' for subject '{SUBJECT}' with the customer's requested "
        "scheme and the customer request's source_id. The server will report a contradiction (contradicts) "
        "because another agent asserted a different value: do NOT pass supersede. Then record ONE decision "
        "resolving it (prefer the security team's scheme for user traffic and say what you do about the "
        "customer's request), with based_on_fact_ids = both auth_method fact ids.",
        files="Read the team memory about authentication. The customer request below asks for something different "
        "from the security note: record the customer's requested auth_method in `memory/facts.md` (keep the "
        "earlier value too, and note the conflict). Then record ONE decision in `memory/decisions.md` resolving "
        "it (prefer the security team's scheme for user traffic and say what you do about the customer's "
        "request), naming both facts.",
    ),
    _t(
        "t06-write-db-schema",
        "Write the database schema",
        "builder",
        25,
        ("t02-choose-api-version", "t04-survey-infra-security"),
        ("db.engine", "db.pool_size", "db.schema_name"),
        "schema.md",
        mcp="Recall 'database' to learn which database the team runs. Write an episode (remember_episode) summarising "
        "the tables you will create (notes, tags, note_tags).",
        files="Read the team memory to learn which database the team runs. Add a note to `memory/log.md` summarising "
        "the tables you will create (notes, tags, note_tags).",
    ),
    _t(
        "t07-implement-crud-spec",
        "Implement the CRUD spec",
        "builder",
        20,
        ("t03-design-endpoints", "t05-choose-auth", "t06-write-db-schema"),
        ("api.base_path", "auth.token_ttl", "auth.session_cookie", "notes.max_length"),
        "crud-spec.md",
        mcp="Recall 'API version' and then recall 'authentication'. After completing, hand off to 'planner' (handoff) "
        "with a short note, the artifact_id and the fact ids you relied on.",
        files="Read the team memory for the API version and the authentication decision. After that, leave a handoff "
        "note for 'planner' in `memory/handoffs.md` naming the artifact and the facts you relied on.",
    ),
    _t(
        "t08-write-test-plan",
        "Write the test plan",
        "researcher",
        15,
        ("t03-design-endpoints",),
        NOTES5,
        "test-plan.md",
        records=NOTES5,
        mcp="Recall 'API version'. The test plan covers the CRUD endpoints and the notes limits.",
        files="Read the team memory for the API version. The test plan covers the CRUD endpoints and the notes limits.",
    ),
    _t(
        "t09-review-spec",
        "Review the spec",
        "planner",
        12,
        ("t07-implement-crud-spec", "t08-write-test-plan"),
        T09_NEEDS,
        "review.md",
        mcp="Recall 'API version' and 'authentication'. Verify the crud-spec artifact with verify_artifact (its "
        "artifact_id is listed under 'Ids from earlier work' as the artifact of t07-implement-crud-spec; if it is "
        "not listed, skip verification). Record ONE decision approving or rejecting the spec, with "
        "based_on_fact_ids = the fact ids you relied on.",
        files="Read the team memory for the API version and authentication, and read the crud-spec artifact of "
        "t07-implement-crud-spec. Record ONE decision in `memory/decisions.md` approving or rejecting the spec, "
        "naming the facts it relies on.",
    ),
    _t(
        "t10-write-docs",
        "Write the API docs",
        "researcher",
        10,
        ("t09-review-spec",),
        ("api.page_size", "api.error_format", "notes.max_length", "users.quota_mb"),
        "docs.md",
        mcp="Recall 'API version'. The docs describe the API for its users.",
        files="Read the team memory for the API version. The docs describe the API for its users.",
    ),
    _t(
        "t11-package-release",
        "Package the release",
        "builder",
        5,
        ("t10-write-docs",),
        REL5,
        "release.md",
        mcp="After completing, hand off to 'planner' (handoff) with a short release note and the artifact_id.",
        files="After that, leave a short release note for 'planner' in `memory/handoffs.md`.",
    ),
    _t(
        "t12-update-endpoints-for-v2",
        "Update endpoint design for API v2",
        "builder",
        60,
        ("t03-design-endpoints",),
        ("api.base_path", "api.cors_origin"),
        "openapi-v2.md",
        mid_run=True,
        mcp="Recall 'API version' (it has changed). Write an episode (remember_episode) listing what changes in the "
        "endpoint design. After completing, hand off to 'planner' (handoff) with a short note, the artifact_id and "
        "the new api_version fact id.",
        files="Read the team memory for the API version (it has changed). Add a note to `memory/log.md` listing what "
        "changes in the endpoint design. After that, leave a handoff note for 'planner' in `memory/handoffs.md` "
        "naming the artifact and the new api_version fact.",
    ),
    _t(
        "t13-reuse-billing-cycle",
        "Reuse the billing cycle and key header from earlier sprints",
        "planner",
        28,
        ("t02-choose-api-version",),
        T13_NEEDS,
        "billing-plan.md",
        mcp="Earlier sprints settled two things this sprint reuses: the billing cycle of the Bolt Billing API decided in "
        "sprint S07, and the API-key header decided in sprint S13. Find both in team memory (recall) and state "
        "them, exactly as recorded, in the artifact next to the code settings. Record ONE decision (record_decision) "
        "to reuse them, with based_on_fact_ids = the fact ids you found.",
        files="Earlier sprints settled two things this sprint reuses: the billing cycle of the Bolt Billing API decided "
        "in sprint S07, and the API-key header decided in sprint S13. Find both in the team's records (the "
        "`history/` folder holds sprints S01-S20) and state them, exactly as recorded, in the artifact next to the "
        "code settings. Record ONE decision in `memory/decisions.md` to reuse them, naming where you found them.",
    ),
    _t(
        "t14-ratelimit-spec",
        "Write the rate-limit spec",
        "researcher",
        22,
        ("t04-survey-infra-security",),
        RL5,
        "ratelimit-spec.md",
        records=RL5[1:],
        extra_docs=("s03_ratelimit_note",),
        mcp=f"Register the S03 note below with add_source (uri 'acme-docs/s03/ratelimit_note.md') and assert predicate "
        f"'ratelimit.window' for subject '{SUBJECT}' with the window value the note states, with its source_id.",
        files="Record in `memory/facts.md` the rate-limit window the S03 note below states, as "
        "`ratelimit.window = VALUE` (source: the S03 note).",
    ),
    _t(
        "t15-config-matrix",
        "Write the configuration matrix",
        "builder",
        18,
        ("t06-write-db-schema", "t14-ratelimit-spec"),
        T15_NEEDS,
        "config-matrix.md",
        mcp=f"Read `repo/ratelimit.py` and assert predicate 'ratelimit.window' for subject '{SUBJECT}' with the value "
        "the code returns now (do NOT pass supersede).",
        files="Read `repo/ratelimit.py` and record in `memory/facts.md` the value `ratelimit.window` returns now.",
    ),
    _t(
        "t16-release-notes",
        "Write the release notes",
        "researcher",
        8,
        ("t09-review-spec", "t13-reuse-billing-cycle", "t15-config-matrix"),
        T16_NEEDS,
        "release-notes.md",
        mcp="The release notes summarise the settings the review, the billing plan and the configuration matrix "
        "relied on. Also state the release channel the team used in sprint S20 (find it in team memory).",
        files="The release notes summarise the settings the review, the billing plan and the configuration matrix "
        "relied on. Also state the release channel the team used in sprint S20 (find it in the team's records).",
    ),
)
TASK_BY_ID = {t.id: t for t in TASKS}
INITIAL_TASKS = tuple(t for t in TASKS if not t.mid_run)

SPECIALS: dict[str, L8Special] = {
    "ingest-v2": L8Special(
        "ingest-v2",
        "researcher",
        ("06_api_style_guide_v2",),
        mcp="A new document was just published (below). Register it with add_source (uri 'acme-docs/<file name>'). It "
        f"replaces the style guide you read earlier: assert predicate 'api_version' for subject '{SUBJECT}' with the "
        "version it prescribes and its source_id (you asserted the old value yourself, so the old fact is "
        "superseded automatically). Then write one episode (remember_episode) saying what changed.",
        files="A new document was just published (below). It replaces the style guide the team read earlier: update "
        "the api_version in `memory/facts.md` to the version it prescribes (note which value it replaces), and "
        "add one line to `memory/log.md` saying what changed.",
    ),  # fmt: skip
    "adopt-v2": L8Special(
        "adopt-v2",
        "planner",
        (),
        mcp="The researcher just updated the 'api_version' fact. Recall 'API version' to get the new fact id. Record ONE "
        "decision (record_decision, task_id 't02-choose-api-version') to adopt the new version, with "
        "based_on_fact_ids = [the new api_version fact id]. Then create exactly one new task with create_tasks: id "
        "'t12-update-endpoints-for-v2', title 'Update endpoint design for API v2', priority 60, depends_on "
        "['t03-design-endpoints'].",
        files="The researcher just updated the api_version in team memory. Read it, and record ONE decision in "
        "`memory/decisions.md` (for task t02-choose-api-version) to adopt the new version, naming the fact. "
        "Then add exactly one new task to `memory/tasks.md`: id 't12-update-endpoints-for-v2', title 'Update "
        "endpoint design for API v2', depends on t03-design-endpoints. (The lead will assign it.)",
    ),  # fmt: skip
}

CONFLICTS = {
    "X1": {"task": "t05-choose-auth", "predicate": "auth_method", "kind": "document",
           "note": "planner (customer request) vs researcher (security note)"},
    "X2": {"task": "t15-config-matrix", "first_task": "t14-ratelimit-spec", "predicate": "ratelimit.window",
           "kind": "old document vs code", "note": "researcher asserts the S03 note's token in t14; builder asserts "
           "the code's token in t15"},
    "X3": {"predicate": "auth.token_ttl", "kind": "post-commit", "note": "a value commit changes auth.token_ttl "
           "while the old fact is live"},
}  # fmt: skip


def s03_note(window_token: str) -> str:
    return (
        "# Sprint S03 rate-limit note\n\n"
        "In sprint S03 the team chose the rate-limit window for the Acme Notes API after load tests. "
        f"The chosen window setting (ratelimit.window) is {window_token}. Burst and per-key limits were left to "
        "the implementation."
    )


def document(stem: str, uri: str, text: str) -> str:
    return f"=== DOCUMENT: {uri} ===\n{text}\n=== END DOCUMENT ==="


def docs_block(stems: tuple[str, ...], extra: dict[str, str] | None = None) -> str:
    base = load_scenario()
    parts = []
    for stem in stems:
        d = base.sources[stem]
        parts.append(document(stem, d.uri, d.text.replace("Acme Notes API", SUBJECT)))
    for stem, text in (extra or {}).items():
        parts.append(document(stem, f"acme-docs/s03/{stem.removeprefix('s03_')}.md", text))
    return ("\n\nDocuments for this assignment:\n\n" + "\n\n".join(parts)) if parts else ""


# ------------------------------------------------------------------------------------------------ conventions
def common_mcp(root: Path | None = None) -> str:
    """The L3 ``common.md`` with the one L8 change (§3.4): files may be read and written, the code may change."""
    base = (Path(__file__).resolve().parents[4] / "demo_data" / "acme" / "roles" / "common.md").read_text(
        encoding="utf-8"
    )
    base = base.replace(
        "All of the team's shared state lives in Plexus, a graph memory and coordination\nservice you reach ONLY "
        "through the `mcp__plexus__*` tools. You have no other tools: no shell, no files, no web.",
        "All of the team's shared state lives in Plexus, a memory and coordination\nservice you reach through the "
        "`mcp__plexus__*` tools. You also have Read, Write, Edit, Glob and Grep (no shell, no web).",
    )
    if "You also have Read" not in base:
        raise AssertionError("common.md changed; the L8 substitution no longer applies")
    base = base.replace('subject "Acme Notes API"', f'subject "{SUBJECT}"')
    return base.rstrip() + "\n" + FILES_SENTENCE + "\n"


FILES_SENTENCE = (
    "9. You may read the repository under `repo/` and write artifacts under `artifacts/`; the code may change during "
    "the sprint."
)

CLAUDE_MD = f"""# Team conventions (Acme Notes API, sprint S21)

You are one member of a three-agent software team (planner, researcher, builder) working on the "{SUBJECT}",
a small notes REST service. Everything in this task is synthetic demo data. You have Read, Write, Edit, Glob and
Grep (no shell, no web).

How to work:
1. Your agent_id and role are given in your assignment. A lead assigns each of you one task per turn.
2. Shared team memory lives in `memory/` (start with `memory/tasks.md`, `memory/facts.md`, `memory/decisions.md`,
   `memory/handoffs.md`, `memory/log.md`; create a file if it does not exist yet). Read it before you act; write what
   the team should remember. The team's records of earlier sprints (S01-S20) are in `history/` (read-only).
3. Recall before you decide: read what the team already knows instead of guessing.
4. Store durable knowledge as short facts (one setting or attribute per line) with where it came from. Do not invent
   facts.
5. Record decisions in `memory/decisions.md`, naming the facts each decision relies on.
6. When your task is finished, record it as done in `memory/tasks.md`. Hand work over in `memory/handoffs.md` only
   when your assignment says so.
7. Be efficient: do what the assignment needs, in order, and do not redo work that is already done.
   When you are done, reply with ONE short sentence summarising what you did.
{FILES_SENTENCE.replace("9. ", "8. ")}
"""


def role_text(role: str) -> str:
    p = Path(__file__).resolve().parents[4] / "demo_data" / "acme" / "roles" / f"{role}.md"
    return p.read_text(encoding="utf-8").replace("Acme Notes API", SUBJECT)


# ------------------------------------------------------------------------------------------------ nominal order
def nominal_order(v2_turn: int = 12) -> list[tuple[int, str]]:
    """The turn at which each task / special would run with no kills and no retries (the scheduler's own order).

    Used only to bias the fault schedule toward functions a not-yet-done task needs (§4.1)."""
    done: set[str] = set()
    created = {t.id for t in INITIAL_TASKS}
    out = [(1, "init")]
    turn, v2_fired, pending = 1, False, []
    while len(done) < len(TASKS):
        turn += 1
        if not v2_fired and turn >= v2_turn:
            v2_fired, pending = True, ["ingest-v2", "adopt-v2"]
        if pending:
            name = pending.pop(0)
            if name == "adopt-v2":
                created.add("t12-update-endpoints-for-v2")
            out.append((turn, name))
            continue
        ready = [
            t for t in TASKS if t.id in created and t.id not in done and all(d in done for d in t.depends_on)
        ]
        ready.sort(key=lambda t: (-t.priority, TASKS.index(t)))
        done.add(ready[0].id)
        out.append((turn, ready[0].id))
    return out


def scenario_json() -> dict[str, Any]:
    return {
        "prompt_version": PROMPT_VERSION,
        "subject": SUBJECT,
        "tasks": [
            {**t.spec(), "role": t.role, "needs": list(t.needs), "records": list(t.records),
             "artifact": t.artifact_path, "docs": list(t.docs) + list(t.extra_docs), "mid_run": t.mid_run,
             "history_needs": HISTORY_NEEDS.get(t.id, {}), "brief_mcp": t.mcp, "brief_files": t.files}
            for t in TASKS
        ],
        "specials": {k: {"role": s.role, "docs": list(s.docs), "brief_mcp": s.mcp, "brief_files": s.files}
                     for k, s in SPECIALS.items()},
        "conflicts": CONFLICTS,
        "nominal_order": nominal_order(),
        "common_mcp": common_mcp(),
        "claude_md": CLAUDE_MD,
    }  # fmt: skip


if __name__ == "__main__":
    print(json.dumps(scenario_json(), indent=1)[:3000])
