"""The deterministic L8 scorer (§6, §9). No LLM anywhere: sentinel tokens are found by string containment.

Input per run (``runs/<seed>/<arm>/``): ``run.json`` (turn table, landed commits, kills, events), ``transcripts/*.jsonl``
(stream-json per turn), ``store_dump.json``, ``artifacts/``, ``memory/`` (B0'); per seed: ``schedule.json``,
``sentinels.json``. Output: ``metrics.json`` per run; :func:`pool` aggregates the seeds per arm.

Time is measured in turns (one ``claude -p`` process = one turn). A commit that "landed before turn T" is visible to
every action in turn T and later.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from statistics import median
from typing import Any

from plexus.crucible.l8 import scenario as S
from plexus.crucible.l8.repo import TOKEN_RE

MCP_PREFIX = "mcp__plexus__"
DONE_RE = re.compile(r"\bdone\b", re.I)
NOT_DONE_RE = re.compile(r"\bnot\s+(yet\s+)?done\b", re.I)
TASK_ID_RE = re.compile(r"^[\s|*-]*`?(t\d\d-[a-z0-9-]+)")
WRITE_ACK_ID = {"assert_fact": "fact_id", "record_decision": "decision_id", "handoff": "handoff_id",
                "verify_fact": "new_fact_id", "complete_task": "task_id"}  # fmt: skip


# ------------------------------------------------------------------------------------------------ events
@dataclass
class Ev:
    turn: int
    agent: str
    name: str  # task id / special / init
    seq: int  # order within the run
    kind: str  # use | result | text
    tool: str = ""  # short name (MCP prefix removed) or file tool name
    mcp: bool = False
    input: dict[str, Any] = field(default_factory=dict)
    text: str = ""  # result content / assistant text
    is_error: bool = False
    use_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)  # parsed JSON result
    result: Ev | None = None  # for a use: its result


def _content_text(c: Any) -> str:
    if isinstance(c, list):
        return "".join(b.get("text", "") for b in c if isinstance(b, dict))
    return c if isinstance(c, str) else json.dumps(c)


def load_events(run_dir: Path) -> list[Ev]:
    out: list[Ev] = []
    seq = 0
    for p in sorted((run_dir / "transcripts").glob("*.jsonl")):
        turn_s, agent, name = p.stem.split("-", 2)
        turn = int(turn_s)
        uses: dict[str, Ev] = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = ev.get("message") if isinstance(ev.get("message"), dict) else {}
            for b in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                if not isinstance(b, dict):
                    continue
                seq += 1
                if b.get("type") == "tool_use":
                    nm = str(b.get("name", ""))
                    e = Ev(turn, agent, name, seq, "use", nm.removeprefix(MCP_PREFIX), nm.startswith(MCP_PREFIX),
                           b.get("input") or {}, use_id=b.get("id", ""))  # fmt: skip
                    uses[e.use_id] = e
                    out.append(e)
                elif b.get("type") == "tool_result":
                    txt = _content_text(b.get("content"))
                    u = uses.get(b.get("tool_use_id", ""))
                    data: dict[str, Any] = {}
                    if u is not None and u.mcp:
                        try:
                            v = json.loads(txt)
                            data = v if isinstance(v, dict) else {}
                        except json.JSONDecodeError:
                            data = {}
                    r = Ev(turn, agent, name, seq, "result", u.tool if u else "", bool(u and u.mcp), text=txt,
                           is_error=bool(b.get("is_error")), use_id=b.get("tool_use_id", ""), data=data)  # fmt: skip
                    if u is not None:
                        u.result = r
                    out.append(r)
                elif b.get("type") == "text" and ev.get("type") == "assistant":
                    out.append(Ev(turn, agent, name, seq, "text", text=str(b.get("text", ""))))
    return out


def ok(e: Ev) -> bool:
    return e.result is not None and not e.result.is_error


def _path(e: Ev) -> str:
    return str(e.input.get("file_path") or e.input.get("path") or "").replace("\\", "/")


def under(e: Ev, folder: str) -> bool:
    return f"/{folder}/" in "/" + _path(e).split("/work/", 1)[-1] or _path(e).startswith(f"{folder}/")


def action_text(e: Ev) -> str | None:
    """The text of a scored action (§6.1), or None if the event is not an action kind."""
    if e.kind != "use":
        return None
    i = e.input
    if e.mcp:
        if e.tool == "complete_task":
            return " ".join(
                str(a.get("summary", "")) for a in (i.get("artifacts") or []) if isinstance(a, dict)
            )
        if e.tool == "record_decision":
            return str(i.get("text", ""))
        if e.tool == "handoff":
            return str(i.get("note", ""))
        if e.tool == "assert_fact":
            return str(i.get("value", ""))
        return None
    if e.tool in ("Write", "Edit") and (under(e, "artifacts") or under(e, "memory")):
        return str(i.get("content") if e.tool == "Write" else i.get("new_string", ""))
    return None


# ------------------------------------------------------------------------------------------------ truth
@dataclass
class Truth:
    """Which token belongs to which function revision, and when each revision became current (actual landings)."""

    rev: dict[str, tuple[str, int]]  # token -> (function, revision index; -1 = the S03 note's value)
    timeline: dict[str, list[tuple[int, str | None]]]  # function -> [(from_turn, token or None=deleted)]
    landed: list[dict[str, Any]]
    last_turn: int

    @classmethod
    def build(cls, run: dict[str, Any], sched: dict[str, Any], sent: dict[str, Any]) -> Truth:
        rev: dict[str, tuple[str, int]] = {}
        timeline: dict[str, list[tuple[int, str | None]]] = {}
        landed = {c["k"]: c["landed_before_turn"] for c in run["commits_landed"]}
        for f, hist in sent["functions"].items():
            tl: list[tuple[int, str | None]] = []
            i = 0
            for h in hist:
                if h.get("from_turn") == -1:
                    rev[h["token"]] = (f, -1)
                    continue
                if h.get("change") is None:
                    tl.append((0, h["token"]))
                    rev[h["token"]] = (f, i)
                    i += 1
                elif h["change"] in landed:
                    tl.append((landed[h["change"]], h["token"]))
                    if h["token"]:
                        rev[h["token"]] = (f, i)
                    i += 1
            timeline[f] = tl
        last = max((t["turn"] for t in run["turns"]), default=0)
        return cls(rev, timeline, run["commits_landed"], last)

    def current(self, f: str, turn: int) -> str | None:
        cur = None
        for t, tok in self.timeline.get(f, []):
            if t <= turn:
                cur = tok
        return cur

    def stale_tokens(self, text: str, turn: int) -> list[str]:
        """Tracked tokens in ``text`` that are stale at ``turn`` and whose function's current token is absent."""
        out = []
        for tok in set(TOKEN_RE.findall(text)):
            if tok not in self.rev:
                continue
            f, _ = self.rev[tok]
            cur = self.current(f, turn)
            if tok != cur and (cur is None or cur not in text):
                out.append(tok)
        return sorted(out)

    def tracked(self, text: str) -> list[str]:
        return sorted({t for t in TOKEN_RE.findall(text) if t in self.rev})

    def func(self, tok: str) -> str:
        return self.rev[tok][0]


# ------------------------------------------------------------------------------------------------ metrics
def wilson(k: int, n: int, z: float = 1.959964) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def score_run(run_dir: Path, seed_dir: Path) -> dict[str, Any]:
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    sched = json.loads((seed_dir / "schedule.json").read_text(encoding="utf-8"))
    sent = json.loads((seed_dir / "sentinels.json").read_text(encoding="utf-8"))
    dump = json.loads((run_dir / "store_dump.json").read_text(encoding="utf-8"))
    arm = run["arm"]
    mcp = arm != "B0p"
    T = Truth.build(run, sched, sent)
    evs = load_events(run_dir)
    uses = [e for e in evs if e.kind == "use"]
    turn_info = {t["turn"]: t for t in run["turns"]}
    reclaim_turns = {t["turn"] for t in run["turns"] if t.get("reclaim_from")}
    killed_turns = {t["turn"] for t in run["turns"] if t.get("killed")}

    # ---- artifact file state as written through the tools (for C2/C3/R3/recovery)
    file_tokens: dict[str, set[str]] = {}
    file_exists_at: dict[str, int] = {}

    def need_ok(task: S.L8Task, toks: set[str], turn: int) -> bool:
        for f in task.needs:
            cur = T.current(f, turn)
            if cur is not None and cur not in toks:
                return False
        return True

    # ---- §6.1 / §6.3 walk
    actions: list[dict[str, Any]] = []
    asserted: set[tuple[str, str, str]] = set()
    completed: dict[str, int] = {}  # task -> turn of the first acknowledged complete_task
    R1 = R2 = R3 = R2_reclaim = 0
    C1 = C2 = 0
    rep_seq: set[int] = set()
    c2_seq: set[int] = set()
    reads_per_turn: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    mem_text: dict[str, str] = {}
    b0_done: dict[str, set[int]] = {}
    R4 = 0
    for e in uses:
        task = S.TASK_BY_ID.get(e.name)
        # R4: the same Read path >= 3 times within one turn, no intervening edit
        if e.tool == "Read":
            c = reads_per_turn[e.turn]
            c[_path(e)] += 1
            if c[_path(e)] == 3:
                R4 += 1
        elif e.tool in ("Write", "Edit"):
            reads_per_turn[e.turn].clear()
        # artifact file tracking + R3/C1
        if e.tool in ("Write", "Edit") and under(e, "artifacts") and ok(e):
            rel = "artifacts/" + _path(e).split("artifacts/", 1)[1]
            tdir = rel.split("/")[1] if rel.count("/") >= 2 else ""
            owner = S.TASK_BY_ID.get(tdir)
            prev = file_tokens.get(rel)
            if e.tool == "Write":
                if (
                    prev is not None
                    and owner is not None
                    and need_ok(owner, prev, e.turn)
                    and e.turn not in reclaim_turns
                ):
                    R3 += 1
                    rep_seq.add(e.seq)
                file_tokens[rel] = set(TOKEN_RE.findall(str(e.input.get("content", ""))))
            else:
                s = set(file_tokens.get(rel, set()))
                s -= set(TOKEN_RE.findall(str(e.input.get("old_string", ""))))
                s |= set(TOKEN_RE.findall(str(e.input.get("new_string", ""))))
                file_tokens[rel] = s
            file_exists_at.setdefault(rel, e.turn)
            if (
                owner
                and owner.id in completed
                and completed[owner.id] < e.turn
                and e.turn not in reclaim_turns
            ):
                C1 += 1
        if e.mcp and e.tool in ("claim_next_task", "heartbeat"):
            tid = str(e.input.get("task_id") or "") or (
                str(((e.result.data or {}).get("task") or {}).get("id", "")) if e.result else ""
            )
            if tid in completed and completed[tid] < e.turn and e.turn not in reclaim_turns:
                C1 += 1
        # R1 / C2
        if e.mcp and e.tool == "complete_task" and ok(e):
            tid = str(e.input.get("task_id", ""))
            if tid in completed:
                R1 += 1
                rep_seq.add(e.seq)
            else:
                completed[tid] = e.turn
            t = S.TASK_BY_ID.get(tid)
            if t is not None:
                toks = file_tokens.get(t.artifact_path)
                if toks is None or not need_ok(t, toks, e.turn):
                    C2 += 1
                    c2_seq.add(e.seq)
        # R2
        if e.mcp and e.tool == "assert_fact" and ok(e):
            k3 = (" ".join(str(e.input.get("subject", "")).lower().split()), str(e.input.get("predicate", "")).strip().lower(),
                  " ".join(str(e.input.get("value", "")).split()))  # fmt: skip
            if k3 in asserted:
                if e.turn in reclaim_turns:
                    R2_reclaim += 1  # attributed to recovery (§6.8), not to step repetition (amendment 3)
                else:
                    R2 += 1
                    rep_seq.add(e.seq)
            asserted.add(k3)
        # scored action? (B0' memory Write: only the lines it adds, the analogue of one assert_fact; §13 amendment)
        txt = action_text(e)
        if txt is not None and not e.mcp and under(e, "memory"):
            rel = _path(e).split("memory/", 1)[1]
            before = mem_text.get(rel, "")
            if e.tool == "Write":
                have = set(before.splitlines())
                txt = chr(10).join(x for x in txt.splitlines() if x not in have)
                if ok(e):
                    mem_text[rel] = str(e.input.get("content", ""))
            else:  # Edit: only the lines new_string adds (anchor lines copied from old_string are not new)
                have = set(str(e.input.get("old_string", "")).splitlines())
                txt = chr(10).join(x for x in txt.splitlines() if x not in have)
            if e.tool == "Edit" and ok(e):
                o = str(e.input.get("old_string", ""))
                mem_text[rel] = (
                    before.replace(o, str(e.input.get("new_string", "")), 1)
                    if o and o in before
                    else before + str(e.input.get("new_string", ""))
                )
            # B0' done marks (amendments 2-3): lines that are new in tasks.md's tracked state after this write (an
            # Edit often rewrites only the status cell, so its new_string alone does not name the task); a line is a
            # record of task X when it is X's table row (title cell) or an 'X: ...' note; reclaim turns excluded
            if ok(e) and rel.endswith("tasks.md"):
                old_lines = set(before.splitlines())
                for line in (x for x in mem_text.get(rel, "").splitlines() if x not in old_lines):
                    m_id = TASK_ID_RE.search(line)
                    tid0 = m_id.group(1) if m_id else ""
                    subject = tid0 in S.TASK_BY_ID and (
                        S.TASK_BY_ID[tid0].title.lower() in line.lower()  # a table row (its title cell)
                        or bool(
                            re.match(r"^[\s*-]*`?" + re.escape(tid0) + r"`?\s*:", line)
                        )  # a 'tid: done' note
                    )  # a dependency list that happens to start a line is not a record of that task
                    if subject and DONE_RE.search(line) and not NOT_DONE_RE.search(line):
                        prev_turns = b0_done.setdefault(tid0, set())
                        if prev_turns and e.turn not in prev_turns and e.turn not in reclaim_turns:
                            R1 += 1
                            rep_seq.add(e.seq)
                        prev_turns.add(e.turn)
                        if tid0 not in completed:
                            completed[tid0] = e.turn
                            t0 = S.TASK_BY_ID[tid0]
                            toks0 = file_tokens.get(t0.artifact_path)
                            if toks0 is None or not need_ok(t0, toks0, e.turn):
                                C2 += 1  # the lead deems it done on the artifact; checked at the done mark
        if txt is None or e.result is None or e.result.is_error:
            continue
        toks = T.tracked(txt)
        if not toks:
            continue
        stale = T.stale_tokens(txt, e.turn)
        dep_funcs = set(task.needs) if task else set()
        dep_toks = [x for x in toks if T.func(x) in dep_funcs]
        actions.append({
            "seq": e.seq, "turn": e.turn, "agent": e.agent, "task": e.name, "tool": e.tool,
            "where": ("artifact" if (not e.mcp and under(e, "artifacts")) else "memory" if not e.mcp else "store"),
            "tokens": toks, "stale": stale, "dependent": bool(dep_toks),
            "dependent_stale": [x for x in stale if T.func(x) in dep_funcs],
            "repetition": e.seq in rep_seq, "c2": e.seq in c2_seq,
            # post-hoc flags (amendment 2), for robustness variants only
            "stale_deleted_only": bool(stale) and all(T.current(T.func(x), e.turn) is None for x in stale),
            "x2_brief_write": bool(stale) and e.name == "t14-ratelimit-spec" and stale == [sched["x2_old_token"]]
            and (e.tool == "assert_fact" or (not e.mcp and under(e, "memory"))),
        })  # fmt: skip

    n_act = len(actions)
    n_stale = sum(1 for a in actions if a["stale"])
    dep = [a for a in actions if a["dependent"]]
    art = [a for a in actions if a["where"] == "artifact" or a["tool"] == "complete_task"]
    art_files = [a for a in actions if a["where"] == "artifact"]
    # propagated: t16 actions copying a stale token that appeared in an earlier artifact write
    earlier_art_tokens: set[str] = set()
    propagated = 0
    t16_actions = 0
    for a in sorted(actions, key=lambda x: x["seq"]):
        if a["task"] == "t16-release-notes":
            t16_actions += 1
            if any(x in earlier_art_tokens for x in a["stale"]):
                propagated += 1
        if a["where"] == "artifact" or a["tool"] == "complete_task":
            earlier_art_tokens |= set(a["tokens"])

    # ---- C3: a task turn that ended with the artifact present and no completion
    C3 = 0
    for tn, ti in turn_info.items():
        if ti["kind"] != "task" or tn in killed_turns:
            continue
        t = S.TASK_BY_ID[ti["name"]]
        present = t.artifact_path in file_tokens and file_exists_at[t.artifact_path] <= tn
        if not present:
            continue
        tu = [e for e in uses if e.turn == tn]
        if mcp:
            done_here = any(e.tool == "complete_task" and ok(e) for e in tu)
        else:
            done_here = tn in b0_done.get(t.id, set())
        if not done_here:
            C3 += 1

    # ---- M1-M3
    M1 = M2 = M3 = 0
    by_turn: dict[int, list[Ev]] = defaultdict(list)
    for e in evs:
        by_turn[e.turn].append(e)
    act_by_seq = {a["seq"]: a for a in actions}
    for tn, es in by_turn.items():
        known: set[str] = set()  # functions whose CURRENT token the agent wrote in its own text
        for e in es:
            if e.kind == "text":
                for tok in T.tracked(e.text):
                    f = T.func(tok)
                    if T.current(f, tn) == tok:
                        known.add(f)
            a = act_by_seq.get(e.seq)
            if a and any(T.func(x) in known for x in a["stale"]):
                M1 += 1
    fact_ids_by_value: dict[str, set[str]] = defaultdict(set)
    for f in dump.get("facts", []):
        fact_ids_by_value[str(f.get("value", "")).strip()].add(f["id"])
    if mcp:
        for e in uses:
            if e.tool == "record_decision" and ok(e):
                based = set(e.input.get("based_on_fact_ids") or [])
                for tok in T.tracked(str(e.input.get("text", ""))):
                    ids = fact_ids_by_value.get(tok, set())
                    if ids and not (ids & based):
                        M2 += 1
                        break
            if (
                e.tool == "handoff"
                and ok(e)
                and T.tracked(str(e.input.get("note", "")))
                and not (e.input.get("fact_ids") or [])
            ):
                M3 += 1

    # ---- §6.2 time to notice
    notices = []
    inval = [c for c in run["commits_landed"] if c["kind"] in ("value", "sibling", "delete")]
    for c in inval:
        Tc = c["landed_before_turn"]
        for f in c["funcs"]:
            old = None
            for t, tok in T.timeline[f]:
                if t < Tc:
                    old = tok
            new = T.current(f, Tc)
            mod = f.split(".")[0]
            l1 = l2 = None
            for e in evs:
                if e.turn < Tc:
                    continue
                hit1 = False
                if e.kind == "use" and e.tool == "Read" and _path(e).endswith(f"repo/{mod}.py"):
                    hit1 = True
                if e.kind == "result" and not e.is_error:
                    if new and new in e.text:
                        hit1 = True
                    if old and _suspect_hit(e.data, old):
                        hit1 = True
                if hit1 and l1 is None:
                    l1 = e.turn
                if e.kind == "use" and new and ok(e):
                    wrote = (e.mcp and e.tool in ("assert_fact", "verify_fact", "complete_task", "record_decision", "handoff")
                             and new in json.dumps(e.input)) or (e.tool in ("Write", "Edit") and new in json.dumps(e.input))  # fmt: skip
                    if wrote and l2 is None:
                        l2 = e.turn
            notices.append({"commit": c["k"], "kind": c["kind"], "function": f, "landed_before_turn": Tc,
                            "level1_turns": None if l1 is None else l1 - Tc,
                            "level2_turns": (None if l2 is None else l2 - Tc) if c["kind"] != "delete" else "n/a (delete)"})  # fmt: skip

    def med(xs: list[Any]) -> float | str | None:
        v = [math.inf if x is None else x for x in xs if x != "n/a (delete)"]
        if not v:
            return None
        m = median(v)
        return "inf" if m == math.inf else m

    # false alarms (P): verify_fact(still_true=true) and facts_to_verify calls
    false_alarm = None
    if arm == "P":
        doc = [c for c in run["commits_landed"] if c["kind"] == "docstring"]
        dt = doc[0]["landed_before_turn"] if doc else None
        fl_by_kind: dict[str, int] = defaultdict(int)
        sha_kind = {c["sha"]: c["kind"] for c in run["commits_landed"]}
        for ch in dump.get("changes", []):
            fl_by_kind[sha_kind.get(ch.get("commit", ""), "other")] += len(ch.get("suspected") or [])
        false_alarm = {
            "verify_still_true_calls": sum(1 for e in uses if e.tool == "verify_fact" and e.input.get("still_true") is True),
            "verify_still_true_after_docstring": sum(1 for e in uses if e.tool == "verify_fact" and e.input.get("still_true") is True and dt and e.turn >= dt),
            "facts_to_verify_calls": sum(1 for e in uses if e.tool == "facts_to_verify"),
            "verify_fact_calls": sum(1 for e in uses if e.tool == "verify_fact"),
            "anchor_fact_calls": sum(1 for e in uses if e.tool == "anchor_fact" and ok(e)),
            "suspected_by_commit_kind": dict(fl_by_kind),
        }  # fmt: skip

    # ---- §6.4 contradictions
    contra = contradictions(uses, evs, T, sched, dump, mcp)

    # ---- §6.6 tokens
    tok = run["claude"]["tokens"]
    total_tokens = sum(int(v) for v in tok.values())
    weighted = (tok.get("input_tokens", 0) + tok.get("output_tokens", 0) + 0.1 * tok.get("cache_read_input_tokens", 0)
                + 1.25 * tok.get("cache_creation_input_tokens", 0))  # fmt: skip
    correct = sum(1 for a in actions if not a["stale"] and not a["repetition"] and not a["c2"])
    cost = float(run["claude"]["total_cost_usd"])

    # ---- §6.7 provenance
    prov = provenance(uses, dump, killed_turns, arm, turn_info)

    # ---- §6.8 recovery
    recov = recovery(run, uses, T, file_tokens_at=_file_state_fn(uses), mcp=mcp, run_dir=run_dir)

    # ---- completion & history recall
    final_art = {t.id: (run_dir / t.artifact_path) for t in S.TASKS}
    tasks_done = _tasks_done(dump, run_dir, mcp)
    hist = {}
    for tid, needs in S.HISTORY_NEEDS.items():
        p = final_art[tid]
        text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        hist[tid] = {lab: all(s.lower() in text.lower() for s in strs) for lab, strs in needs.items()}

    # stale facts live in the store at end
    end_turn = T.last_turn + 1
    live_stale = 0
    if mcp:
        for f in dump.get("facts", []):
            v = str(f.get("value", "")).strip()
            if (
                v in T.rev
                and T.stale_tokens(v, end_turn)
                and f.get("status") == "active"
                and f.get("verify_state", "verified") != "suspect"
            ):
                live_stale += 1
    else:
        facts_md = (dump.get("memory_files") or {}).get("memory/facts.md", "")
        for line in facts_md.splitlines():
            if re.search(r"[\w.]+\s*[=:]\s*`?AX-\d{5}", line) and "supersed" not in line.lower():
                live_stale += bool(T.stale_tokens(line, end_turn))

    n_dep_stale = sum(1 for a in dep if a["dependent_stale"])
    reps = R1 + R2 + R3
    return {
        "seed": run["seed"], "arm": arm, "status": run["status"], "error": run.get("error", ""),
        "turns": len(run["turns"]), "tasks_done": tasks_done, "tasks_total": len(S.TASKS),
        "commits_landed": len(run["commits_landed"]), "kills_fired": run["kills_fired"],
        "hook_failed_commits": run.get("hook_failed_commits", []),
        "stale_act": {"scored_actions": n_act, "stale": n_stale, "rate": rate(n_stale, n_act), "wilson95": wilson(n_stale, n_act),
                      "dependent": {"n": len(dep), "stale": n_dep_stale, "rate": rate(n_dep_stale, len(dep))},
                      "artifact_and_completion": {"n": len(art), "stale": sum(1 for a in art if a["stale"]),
                                                  "rate": rate(sum(1 for a in art if a["stale"]), len(art))},
                      "artifact_files_only": {"n": len(art_files), "stale": sum(1 for a in art_files if a["stale"]),
                                              "rate": rate(sum(1 for a in art_files if a["stale"]), len(art_files))},
                      "propagated_t16": {"n": t16_actions, "propagated": propagated},
                      "post_hoc": _post_hoc(actions),
                      "stale_facts_live_at_end": live_stale},
        "time_to_notice": {"cases": notices, "level1_median_turns": med([n["level1_turns"] for n in notices]),
                           "level2_median_turns": med([n["level2_turns"] for n in notices]),
                           "level1_censored": sum(1 for n in notices if n["level1_turns"] is None),
                           "level2_censored": sum(1 for n in notices if n["level2_turns"] is None),
                           "false_alarm": false_alarm},
        "mast": {"R1": R1, "R2": R2 if mcp else "n/a (no assert)", "R2_in_reclaim_turns": R2_reclaim if mcp else "n/a", "R3": R3, "R4_wasted_reads": R4,
                 "step_repetition_rate": rate(reps if mcp else R1 + R3, n_act),
                 "C1": C1, "C2": C2, "C3": C3, "missing_completion_rate": rate(C1 + C2 + C3, len(S.TASKS)),
                 "M1": M1, "M2": M2 if mcp else "n/a (no decision object)", "M3": M3 if mcp else "n/a (no handoff object)",
                 "mismatch_rate": rate(M1 + M2 + M3, n_act)},
        "contradictions": contra,
        "tokens": {"total": total_tokens, "billing_weighted": round(weighted), "cost_usd": cost,
                   "correct_actions": correct, "per_correct_action": round(total_tokens / correct) if correct else None,
                   "weighted_per_correct_action": round(weighted / correct) if correct else None,
                   "per_scored_action": round(total_tokens / n_act) if n_act else None,
                   "cost_per_correct_action": round(cost / correct, 4) if correct else None},
        "provenance": prov,
        "recovery": recov,
        "history_recall": hist,
        "actions": actions,
    }  # fmt: skip


def _post_hoc(actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Robustness variants added after the gate run (amendment 2); never the headline."""
    out = {}
    for name, drop in (
        ("excl_x2_brief_write", lambda a: a["x2_brief_write"]),
        ("excl_deleted_only", lambda a: a["stale_deleted_only"]),
        ("excl_both", lambda a: a["x2_brief_write"] or a["stale_deleted_only"]),
    ):
        keep = [a for a in actions if not drop(a)]
        k = sum(1 for a in keep if a["stale"])
        out[name] = {"n": len(keep), "stale": k, "rate": rate(k, len(keep))}
    return out


def common_task_rate(metrics: list[dict[str, Any]], tasks: set[str]) -> dict[str, Any]:
    """Post-hoc: stale-act rate over actions of ``tasks`` only (tasks every arm of the seed reached)."""
    acts = [a for m in metrics for a in m["actions"] if a["task"] in tasks]
    k = sum(1 for a in acts if a["stale"])
    return {"n": len(acts), "stale": k, "rate": rate(k, len(acts))}


def _suspect_hit(data: Any, old: str) -> bool:
    """A tool result (JSON) that returns a fact with value ``old`` flagged suspect / with a change id."""
    if isinstance(data, dict):
        if str(data.get("value", "")).strip() == old and (
            data.get("verify_state") == "suspect" or data.get("change_id")
        ):
            return True
        return any(_suspect_hit(v, old) for v in data.values())
    if isinstance(data, list):
        return any(_suspect_hit(v, old) for v in data)
    return False


def _file_state_fn(uses: list[Ev]):  # noqa: ANN202
    """f(path, seq) -> tokens of an artifact file just after event seq (as written through the tools)."""
    hist: dict[str, list[tuple[int, set[str]]]] = defaultdict(list)
    cur: dict[str, set[str]] = {}
    for e in uses:
        if e.tool in ("Write", "Edit") and under(e, "artifacts") and ok(e):
            rel = "artifacts/" + _path(e).split("artifacts/", 1)[1]
            if e.tool == "Write":
                cur[rel] = set(TOKEN_RE.findall(str(e.input.get("content", ""))))
            else:
                s = set(cur.get(rel, set()))
                s -= set(TOKEN_RE.findall(str(e.input.get("old_string", ""))))
                s |= set(TOKEN_RE.findall(str(e.input.get("new_string", ""))))
                cur[rel] = s
            hist[rel].append((e.seq, set(cur[rel])))

    def at(path: str, seq: int) -> set[str] | None:
        last = None
        for s, toks in hist.get(path, []):
            if s <= seq:
                last = toks
        return last

    return at


def _tasks_done(dump: dict[str, Any], run_dir: Path, mcp: bool) -> int:
    if mcp:
        st = {t["id"]: t["status"] for t in dump.get("tasks", [])}
        return sum(1 for t in S.TASKS if st.get(t.id) == "done")
    return sum(1 for t in S.TASKS if (run_dir / t.artifact_path).exists())


def contradictions(
    uses: list[Ev], evs: list[Ev], T: Truth, sched: dict[str, Any], dump: dict[str, Any], mcp: bool
) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def first_both(after_seq: int, a: str, b: str, ci: bool = False) -> int | None:
        for e in evs:
            if e.seq <= after_seq:
                continue
            if e.kind in ("result", "text"):
                txt = e.text or ""
            elif e.kind == "use" and (
                (e.mcp and e.tool == "record_decision")
                or (not e.mcp and e.tool in ("Write", "Edit") and under(e, "memory"))
            ):
                txt = json.dumps(e.input)
            else:
                continue
            t2 = txt.lower() if ci else txt
            if (a.lower() if ci else a) in t2 and (b.lower() if ci else b) in t2:
                return e.turn
        return None

    # X1 (keywords; documents give 'JWT' vs 'API key')
    x1 = [e for e in uses if ok(e) and e.name == "t05-choose-auth" and (
          (e.mcp and e.tool == "assert_fact" and str(e.input.get("predicate", "")).strip().lower() == "auth_method")
          or (not e.mcp and e.tool in ("Write", "Edit") and under(e, "memory")
              and re.search(r"api[ -]?key", str(e.input.get("new_string") or e.input.get("content") or ""), re.I)))]  # fmt: skip
    if x1:
        e = x1[0]
        t2 = e.turn
        at_write = bool(mcp and e.result and (e.result.data.get("contradicts")))
        surf = t2 if at_write else first_both(e.seq, "JWT", "API key", ci=True)
        out["X1"] = {"second_assertion_turn": t2, "surfaced_at_write": at_write,
                     "latency_turns": None if surf is None else surf - t2, "method": "keywords 'JWT' and 'API key'"}  # fmt: skip
    else:
        out["X1"] = {"second_assertion_turn": None, "latency_turns": None, "note": "no auth assertion in t05"}
    # X2 (tokens): old S03 token vs the code's token of ratelimit.window at the time
    old = sched["x2_old_token"]
    code_toks = {tok for tok, (f, i) in T.rev.items() if f == "ratelimit.window" and i >= 0}
    first_old = next(
        (e for e in uses if ok(e) and old in json.dumps(e.input) and _is_store_write(e, mcp)), None
    )
    second = None
    if first_old is not None:
        second = next((e for e in uses if ok(e) and e.seq > first_old.seq and _is_store_write(e, mcp)
                       and any(c in json.dumps(e.input) for c in code_toks) and e.agent != first_old.agent), None)  # fmt: skip
    if second is not None:
        at_write = bool(mcp and second.result and second.result.data.get("contradicts"))
        code_tok = next(c for c in code_toks if c in json.dumps(second.input))
        surf = second.turn if at_write else first_both(second.seq, old, code_tok)
        post_use = sum(
            1
            for e in uses
            if e.seq > second.seq and old in (action_text(e) or "") and e.result and not e.result.is_error
        )
        out["X2"] = {"first_turn": first_old.turn, "second_assertion_turn": second.turn, "surfaced_at_write": at_write,
                     "latency_turns": None if surf is None else surf - second.turn,
                     "post_conflict_actions_using_old": post_use,
                     "both_live_at_end": _both_live(dump, mcp, old, code_tok)}  # fmt: skip
    else:
        out["X2"] = {"first_turn": first_old.turn if first_old else None, "second_assertion_turn": None,
                     "latency_turns": None, "note": "the conflicting pair was not both written to the store"}  # fmt: skip
    # X3: auth.token_ttl changed by a value commit while the old fact is live
    tl = T.timeline.get("auth.token_ttl", [])
    if len(tl) >= 2:
        Tc, new = tl[1]
        old3 = tl[0][1]
        w = next(
            (
                e
                for e in uses
                if ok(e) and e.turn >= Tc and new and new in json.dumps(e.input) and _is_store_write(e, mcp)
            ),
            None,
        )
        if w is not None:
            res = w.result.data if w.result else {}
            out["X3"] = {"commit_turn": Tc, "new_value_written_turn": w.turn, "via": w.tool,
                         "contradicts_at_write": bool(res.get("contradicts")), "superseded_at_write": bool(res.get("superseded")) or w.tool == "verify_fact",
                         "both_live_at_end": _both_live(dump, mcp, old3, new)}  # fmt: skip
        else:
            out["X3"] = {"commit_turn": Tc, "new_value_written_turn": None, "both_live_at_end": None,
                         "note": "nobody wrote the new auth.token_ttl to the store"}  # fmt: skip
    return out


def _is_store_write(e: Ev, mcp: bool) -> bool:
    if mcp:
        return e.mcp and e.tool in ("assert_fact", "verify_fact")
    return e.tool in ("Write", "Edit") and under(e, "memory")


def _both_live(dump: dict[str, Any], mcp: bool, a: str, b: str) -> bool | None:
    if not mcp:
        txt = "\n".join((dump.get("memory_files") or {}).values())
        return a in txt and b in txt
    live = {str(f.get("value", "")).strip() for f in dump.get("facts", []) if f.get("status") == "active"}
    return a in live and b in live


def provenance(uses: list[Ev], dump: dict[str, Any], killed_turns: set[int], arm: str,
               turn_info: dict[int, dict[str, Any]]) -> dict[str, Any]:  # fmt: skip
    """§6.7: an acknowledged write has a provenance record if the store holds a WROTE row to its node by the acting
    agent with a step time inside the turn (amendment 3: a row from an earlier step, e.g. the kickoff create_tasks
    of a Task node, does not count)."""
    if arm == "B0p":
        return {"overall": "n/a (no provenance model)"}
    wrote: dict[str, list[tuple[str, int, int | None]]] = defaultdict(list)
    for w in dump.get("wrote_steps") or dump.get("wrote", []):
        try:
            n = w.get("n")
            wrote[str(w["node"])].append(
                (str(w.get("agent") or ""), int(w.get("at") or 0), None if n is None else int(n))
            )
        except (TypeError, ValueError):
            continue
    per: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    kill = [0, 0]
    lost = []
    dup_acks = 0
    for e in uses:
        if not (e.mcp and e.tool in WRITE_ACK_ID and ok(e)):
            continue
        d = e.result.data if e.result else {}
        if e.tool == "assert_fact" and d.get("duplicate_of"):
            dup_acks += 1
            continue
        nid = e.input.get("task_id") if e.tool == "complete_task" else d.get(WRITE_ACK_ID[e.tool])
        if not nid:
            continue
        ti = turn_info.get(e.turn, {})
        lo, hi = int(ti.get("start_ms") or 0), int(ti.get("end_ms") or 10**15) + 5000
        step_n = e.input.get("step")
        rows = wrote.get(str(nid), [])
        if step_n is not None and any(n is not None for _, _, n in rows):
            # P keys a Step by (agent, n); the S21 step numbers restart at 1 and merge into the history's Steps of
            # the same number (amendment 3), so the Step's time is the history's: match on the number instead
            has = any(a == e.agent and n == int(step_n) for a, _, n in rows)
        else:
            has = any(a == e.agent and lo <= at <= hi for a, at, _ in rows)
        per[e.tool][0] += has
        per[e.tool][1] += 1
        if e.tool != "complete_task" and e.turn in killed_turns:
            kill[0] += has
            kill[1] += 1
        if not has:
            lost.append({"turn": e.turn, "tool": e.tool, "id": nid})
    core = [v for k, v in per.items() if k != "complete_task"]
    tot = [sum(v[0] for v in core), sum(v[1] for v in core)]
    return {"overall": {"with_record": tot[0], "acknowledged": tot[1], "rate": rate(*tot),
                        "tools": "assert_fact, record_decision, handoff, verify_fact (complete_task per tool only)",
                        "rule_of_three_upper_bound_missing": round(3 / tot[1], 4) if tot[1] and tot[0] == tot[1] else None},
            "by_tool": {k: {"with_record": v[0], "acknowledged": v[1], "rate": rate(*v)} for k, v in per.items()},
            "kill_turns": {"with_record": kill[0], "acknowledged": kill[1], "rate": rate(*kill)},
            "duplicate_acks_skipped": dup_acks,
            "without_record": lost[:50]}  # fmt: skip


def recovery(
    run: dict[str, Any], uses: list[Ev], T: Truth, *, file_tokens_at: Any, mcp: bool, run_dir: Path
) -> list[dict[str, Any]]:
    out = []
    kills = [e for e in run["events"] if e["event"] == "kill"]
    for k in kills:
        kt, tid = k["turn"], k["task"]
        t = S.TASK_BY_ID.get(tid)
        if t is None:
            continue
        last_seq = max((e.seq for e in uses if e.turn == kt), default=0)
        toks = file_tokens_at(t.artifact_path, last_seq)
        finished = toks is not None and all(
            (T.current(f, kt) is None or T.current(f, kt) in toks) for f in t.needs
        )
        later = [e for e in uses if e.turn > kt and e.name == tid]
        rt = min((e.turn for e in later), default=None)
        repeats = sum(
            1 for e in later if e.turn == rt and e.tool == "Write" and t.artifact_path in _path(e) and ok(e)
        )
        dead_facts = {
            str(e.input.get("value")) for e in uses if e.turn == kt and e.tool == "assert_fact" and ok(e)
        }
        reasserts = sum(
            1
            for e in later
            if e.turn == rt and e.tool == "assert_fact" and str(e.input.get("value")) in dead_facts
        )
        if mcp:
            done_turn = min((e.turn for e in uses if e.turn >= kt and e.tool == "complete_task" and ok(e)
                             and e.input.get("task_id") == tid), default=None)  # fmt: skip
        else:
            done_turn = rt if (run_dir / t.artifact_path).exists() and rt else None
        out.append({"kill": k["kill"], "turn": kt, "task": tid, "agent": k["agent"],
                    "finished_units": int(finished), "repeated_units": min(repeats, 1) if finished else 0,
                    "rewrites_in_reclaim_turn": repeats, "reasserted_facts": reasserts,
                    "reclaim_turn": rt, "recovered": done_turn is not None,
                    "turns_kill_to_done": None if done_turn is None else done_turn - kt})  # fmt: skip
    return out


# ------------------------------------------------------------------------------------------------ pooling
def perm_test(a: list[float], b: list[float]) -> float | None:
    """Exact two-sided permutation test on the difference of means (all C(n+m, n) splits)."""
    if not a or not b:
        return None
    allv = a + b
    n = len(a)
    obs = abs(sum(a) / len(a) - sum(b) / len(b))
    hits = tot = 0
    for idx in combinations(range(len(allv)), n):
        s = set(idx)
        x = [allv[i] for i in s]
        y = [allv[i] for i in range(len(allv)) if i not in s]
        d = abs(sum(x) / len(x) - sum(y) / len(y))
        hits += d >= obs - 1e-12
        tot += 1
    return round(hits / tot, 4)


def pool(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in metrics:
        by_arm[m["arm"]].append(m)
    arms: dict[str, Any] = {}
    for arm, ms in sorted(by_arm.items()):
        ms = sorted(ms, key=lambda m: m["seed"])

        def seedvals(fn: Any, ms: list[dict[str, Any]] = ms) -> list[Any]:
            return [fn(m) for m in ms]

        def mmm(vals: list[Any]) -> dict[str, Any]:
            vals = [math.inf if x == "inf" else x for x in vals]
            v = [x for x in vals if isinstance(x, (int, float))]
            return {
                "values": vals,
                "min": min(v) if v else None,
                "median": median(v) if v else None,
                "max": max(v) if v else None,
            }

        k = sum(m["stale_act"]["stale"] for m in ms)
        n = sum(m["stale_act"]["scored_actions"] for m in ms)
        reps = sum(
            (m["mast"]["R1"] + (m["mast"]["R2"] if isinstance(m["mast"]["R2"], int) else 0) + m["mast"]["R3"])
            for m in ms
        )
        arms[arm] = {
            "seeds": [m["seed"] for m in ms],
            "stale_act": {"pooled": rate(k, n), "stale": k, "n": n, "wilson95": wilson(k, n),
                          "seed_rates": mmm(seedvals(lambda m: m["stale_act"]["rate"])),
                          "dependent_pooled": rate(sum(m["stale_act"]["dependent"]["stale"] for m in ms), sum(m["stale_act"]["dependent"]["n"] for m in ms)),
                          "artifact_files_pooled": rate(sum(m["stale_act"]["artifact_files_only"]["stale"] for m in ms), sum(m["stale_act"]["artifact_files_only"]["n"] for m in ms)),
                          "stale_facts_live_at_end": mmm(seedvals(lambda m: m["stale_act"]["stale_facts_live_at_end"]))},
            "step_repetition": {"pooled": rate(reps, n), "events": reps, "seed_rates": mmm(seedvals(lambda m: m["mast"]["step_repetition_rate"]))},
            "missing_completion": mmm(seedvals(lambda m: m["mast"]["C1"] + m["mast"]["C2"] + m["mast"]["C3"])),
            "mismatch": {"M1": sum(m["mast"]["M1"] for m in ms),
                         "M2": sum(m["mast"]["M2"] for m in ms) if all(isinstance(m["mast"]["M2"], int) for m in ms) else "n/a",
                         "M3": sum(m["mast"]["M3"] for m in ms) if all(isinstance(m["mast"]["M3"], int) for m in ms) else "n/a",
                         "seed_rates": mmm(seedvals(lambda m: m["mast"]["mismatch_rate"]))},
            "time_to_notice": {"level1_median": mmm(seedvals(lambda m: m["time_to_notice"]["level1_median_turns"])),
                               "level2_median": mmm(seedvals(lambda m: m["time_to_notice"]["level2_median_turns"])),
                               "level1_censored": sum(m["time_to_notice"]["level1_censored"] for m in ms),
                               "level2_censored": sum(m["time_to_notice"]["level2_censored"] for m in ms),
                               "cases": sum(len(m["time_to_notice"]["cases"]) for m in ms)},
            "tokens": {"total": mmm(seedvals(lambda m: m["tokens"]["total"])),
                       "per_correct_action": mmm(seedvals(lambda m: m["tokens"]["per_correct_action"])),
                       "weighted_per_correct_action": mmm(seedvals(lambda m: m["tokens"]["weighted_per_correct_action"])),
                       "cost_usd": round(sum(m["tokens"]["cost_usd"] for m in ms), 4),
                       "pooled_per_correct_action": _ratio(sum(m["tokens"]["total"] for m in ms), sum(m["tokens"]["correct_actions"] for m in ms)),
                       "pooled_weighted_per_correct_action": _ratio(sum(m["tokens"]["billing_weighted"] for m in ms), sum(m["tokens"]["correct_actions"] for m in ms))},
            "tasks_done": mmm(seedvals(lambda m: m["tasks_done"])),
            "turns": mmm(seedvals(lambda m: m["turns"])),
        }  # fmt: skip
    tests = {}
    if "P" in arms:
        for other in ("B1", "B0p"):
            if other not in arms:
                continue
            for metric, fn in (
                ("stale_act", lambda a: a["stale_act"]["seed_rates"]["values"]),
                ("step_repetition", lambda a: a["step_repetition"]["seed_rates"]["values"]),
            ):
                pa = [x for x in fn(arms["P"]) if x is not None]
                pb = [x for x in fn(arms[other]) if x is not None]
                p = perm_test(pa, pb)
                overlap = bool(pa and pb and not (max(pa) < min(pb) or max(pb) < min(pa)))
                tests[f"P_vs_{other}_{metric}"] = {"P": pa, other: pb, "perm_p": p, "ranges_overlap": overlap,
                                                   "P_lower": bool(pa and pb and median(pa) < median(pb)), "separated": (p is not None and p <= 0.05 and not overlap)}  # fmt: skip
    return {"arms": arms, "tests": tests}


def _ratio(a: float, b: float) -> int | None:
    return round(a / b) if b else None


def score_all(out: Path, arms: tuple[str, ...] = ("P", "B1", "B0p")) -> dict[str, Any]:
    """Score every finished run under ``out/runs`` (writes ``metrics.json`` next to each ``run.json``) and pool."""
    metrics = []
    for run_json in sorted((out / "runs").glob("*/*/run.json")):
        run_dir = run_json.parent
        if run_dir.name not in arms:
            continue
        m = score_run(run_dir, out / "seeds" / run_dir.parent.name)
        (run_dir / "metrics.json").write_text(
            json.dumps(m, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
        )
        metrics.append(m)
    return {"runs": [{k: m[k] for k in ("seed", "arm", "status")} for m in metrics], **pool(metrics)}


def redump_p_steps(run_dir: Path, host: str = "127.0.0.1", port: int = 6365) -> int:
    """Add ``wrote_steps`` (node, agent, step n, at) to a P run's store_dump.json from its (unchanged) tenant graph.

    The runner's dump kept WROTE rows without the Step number; amendment 3 matches provenance on it. Read-only."""
    from plexus.graph.client import GraphClient
    from plexus.graph.tenancy import graph_name

    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    p = run_dir / "store_dump.json"
    dump = json.loads(p.read_text(encoding="utf-8"))
    gc = GraphClient(host=host, port=port)
    try:
        rows = (
            gc.graph(graph_name(run["tenant"]))
            .ro_query("MATCH (s:Step)-[:WROTE]->(x) RETURN x.id, s.agent_id, s.n, s.at")
            .result_set
        )
    finally:
        gc.close()
    dump["wrote_steps"] = [{"node": r[0], "agent": r[1], "n": r[2], "at": r[3]} for r in rows]
    p.write_text(json.dumps(dump, indent=0, default=str) + "\n", encoding="utf-8")
    return len(rows)
