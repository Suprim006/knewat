"""B0 Files: how Claude Code and Hermes coordinate today, built competently (BASELINE §0, "not a strawman").

Layout per tenant, ``<root>/B0/<tenant>/``::

    MEMORY.md          markdown memory file, one bullet per fact (+ a JSON metadata comment); guarded by memory.lock
    sources.json       registered sources (guarded by memory.lock)
    tasks.json         the task list incl. deps, leases, versions, artifacts; guarded by tasks.lock
    decisions.jsonl    append-only decision log
    handoffs.jsonl     append-only handoff log
    agents/<agent>     one marker file per registered agent
    logs/<agent>.jsonl append-only per-agent transcript of every tool call (O_APPEND, single-writer per file)

Concurrency: every read-modify-write holds an inter-process lock file (``flock`` / ``msvcrt.locking``; released by
the OS if the holder is killed), and the new content is written to a temp file and ``os.replace``d in, so a crash can
never leave a half-written list. There are no transactions across files: a handoff checks its references in
``tasks.json`` and ``MEMORY.md`` one after the other (ids are never deleted, so the check cannot go stale).
``why`` and ``knew_at`` raise :class:`Unsupported`: the files hold the evidence but no queryable links, so
Layer 2 has an LLM read them.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.parse
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from plexus.crucible.api import (
    OPEN,
    ClaimConflict,
    UnknownReference,
    Unsupported,
    valid_tenant,
)
from plexus.crucible.util import (
    FileLock,
    classify,
    fact_text,
    keyword_score,
    new_id,
    normalize,
    now_ms,
    scope_chain,
    words,
)

MEMORY_HEADER = (
    "# Shared team memory\n"
    "<!-- One fact per bullet. The JSON comment is the machine-readable record. Edit through the tools only. -->\n"
)


def _safe(name: str) -> str:
    """A file-system safe, collision-free file name for an arbitrary agent id."""
    return urllib.parse.quote(name, safe="") or "_"


def _dump(obj: Any) -> str:
    # '<' is escaped so a metadata comment can never contain '-->' or '<!--' from user text
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c")


class FilesBackend:
    name = "B0"
    label = "Files"
    capabilities = frozenset({"as_of", "contradictions", "forget_cascade", "dependencies"})
    isolation = "one directory per tenant; the tenant name is validated before it becomes a path"

    def __init__(self, tenant: str, root: str | os.PathLike[str]):
        self.tenant = valid_tenant(tenant)
        self.dir = Path(root) / self.name / self.tenant
        (self.dir / "agents").mkdir(parents=True, exist_ok=True)
        (self.dir / "logs").mkdir(exist_ok=True)
        self._tasks_lock = FileLock(self.dir / "tasks.lock")
        self._mem_lock = FileLock(self.dir / "memory.lock")
        self._tasks_path = self.dir / "tasks.json"
        self._mem_path = self.dir / "MEMORY.md"
        self._src_path = self.dir / "sources.json"
        self._tmp_n = 0
        self._tmp_lock = threading.Lock()

    def close(self) -> None:
        return None

    # -- low-level file helpers ------------------------------------------------------------------------------
    def _atomic_write(self, path: Path, text: str) -> None:
        with self._tmp_lock:
            self._tmp_n += 1
            n = self._tmp_n
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.{n}.tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, path)

    def _append(self, path: Path, line: str) -> None:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)

    def _log(self, agent_id: str, tool: str, **fields: Any) -> None:
        self._append(
            self.dir / "logs" / f"{_safe(agent_id)}.jsonl", _dump({"ts": now_ms(), "tool": tool, **fields})
        )

    # tasks --------------------------------------------------------------------------------------------------
    def _load_tasks(self) -> dict[str, Any]:
        if not self._tasks_path.exists():
            return {"next_seq": 0, "tasks": {}}
        return json.loads(self._tasks_path.read_text(encoding="utf-8"))

    def _save_tasks(self, data: dict[str, Any]) -> None:
        self._atomic_write(self._tasks_path, json.dumps(data, separators=(",", ":")))

    # memory -------------------------------------------------------------------------------------------------
    def _load_facts(self) -> list[dict[str, Any]]:
        if not self._mem_path.exists():
            return []
        facts = []
        for line in self._mem_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("- ") and " <!--" in line:
                facts.append(json.loads(line.rsplit(" <!--", 1)[1].removesuffix("-->")))
        return facts

    def _save_facts(self, facts: Sequence[dict[str, Any]]) -> None:
        lines = [MEMORY_HEADER]
        for f in facts:
            human = f"- **{f['entity_name']}** {f['predicate']}: {f['value']} ({f['status']}, {f['scope']})"
            human = human.replace("<!--", "< !--").replace("\n", " ")
            lines.append(f"{human} <!--{_dump(f)}-->\n")
        self._atomic_write(self._mem_path, "".join(lines))

    def _load_sources(self) -> dict[str, Any]:
        if not self._src_path.exists():
            return {}
        return json.loads(self._src_path.read_text(encoding="utf-8"))

    # -- agents ----------------------------------------------------------------------------------------------
    def register_agent(self, agent_id: str, role: str = "") -> None:
        (self.dir / "agents" / _safe(agent_id)).write_text(role, encoding="utf-8")
        self._log(agent_id, "register_agent", role=role)

    def _agent_exists(self, agent_id: str) -> bool:
        return (self.dir / "agents" / _safe(agent_id)).exists()

    # -- memory ----------------------------------------------------------------------------------------------
    def remember_episode(self, agent_id: str, text: str, step: int | None = None) -> str:
        eid = new_id()
        self._log(agent_id, "episode", id=eid, step=step, text=text)
        return eid

    def add_source(self, uri: str, kind: str = "doc", trust: float = 1.0) -> str:
        if not uri.strip():
            raise ValueError("source uri must not be empty")
        with self._mem_lock.hold():
            src = self._load_sources()
            for sid, s in src.items():
                if s["uri"] == uri:
                    return sid
            sid = new_id()
            src[sid] = {"uri": uri, "kind": kind, "trust": trust, "created_at": now_ms()}
            self._atomic_write(self._src_path, json.dumps(src, separators=(",", ":")))
            return sid

    def assert_fact(
        self,
        agent_id: str,
        subject: str,
        predicate: str,
        value: str,
        scope: str = "global",
        source_id: str | None = None,
        derived_from: Sequence[str] = (),
        confidence: float = 1.0,
        supersede: bool = False,
        now: int | None = None,
    ) -> dict[str, Any]:
        entity, pred, norm_value = normalize(subject), normalize(predicate), normalize(value)
        if not entity or not pred or not norm_value:
            raise ValueError("subject, predicate and value must not be empty")
        scope_chain(scope)
        t = now if now is not None else now_ms()
        origins = list(dict.fromkeys([*([source_id] if source_id else []), *derived_from]))
        with self._mem_lock.hold():
            facts = self._load_facts()
            if origins:
                known = set(self._load_sources()) | {f["id"] for f in facts}
                for o in origins:
                    if o not in known:
                        raise UnknownReference(f"unknown origin id: {o}")
            by_id = {f["id"]: f for f in facts}
            cur = [
                f
                for f in facts
                if f["entity"] == entity
                and f["predicate"] == pred
                and f["scope"] == scope
                and f["status"] == "active"
                and f["valid_to"] == OPEN
            ]
            dup, closing, clashing, ts = classify(cur, agent_id, norm_value, supersede, t)
            if dup is not None:
                d = by_id[dup["id"]]
                if agent_id not in d["asserted_by"]:
                    d["asserted_by"].append(agent_id)
                d["derived_from"] = list(dict.fromkeys([*d["derived_from"], *origins]))
                for f in closing:
                    o = by_id[f["id"]]
                    o["valid_to"], o["status"] = ts, "superseded"
                    d["supersedes"].append(o["id"])
                result = {
                    "fact_id": d["id"],
                    "duplicate_of": d["id"],
                    "superseded": [f["id"] for f in closing],
                    "contradicts": [],
                }
            else:
                fid = new_id()
                name = next(
                    (f["entity_name"] for f in facts if f["entity"] == entity), " ".join(subject.split())
                )
                for f in closing:
                    o = by_id[f["id"]]
                    o["valid_to"], o["status"] = ts, "superseded"
                facts.append(
                    {
                        "id": fid,
                        "entity": entity,
                        "entity_name": name,
                        "predicate": pred,
                        "value": " ".join(value.split()),
                        "norm_value": norm_value,
                        "scope": scope,
                        "status": "active",
                        "valid_from": ts,
                        "valid_to": OPEN,
                        "recorded_at": t,
                        "confidence": confidence,
                        "asserted_by": [agent_id],
                        "derived_from": origins,
                        "supersedes": [f["id"] for f in closing],
                        "contradicts": [f["id"] for f in clashing],
                    }
                )
                result = {
                    "fact_id": fid,
                    "duplicate_of": None,
                    "superseded": [f["id"] for f in closing],
                    "contradicts": [f["id"] for f in clashing],
                }
            self._save_facts(facts)
        self._log(
            agent_id, "assert_fact", subject=subject, predicate=predicate, value=value, scope=scope, **result
        )
        return result

    def recall(
        self, agent_id: str, query: str, scope: str = "global", k: int = 8, as_of: int | None = None
    ) -> list[dict[str, Any]]:
        if k <= 0:
            return []
        k = min(k, 50)
        chain, t = scope_chain(scope), as_of if as_of is not None else now_ms()
        statuses = ("active",) if as_of is None else ("active", "superseded")
        qwords = list(dict.fromkeys(w for w in words(query) if len(w) >= 2))[:10]
        with self._mem_lock.hold():
            facts = self._load_facts()
        scored = []
        for f in facts:
            if f["scope"] in chain and f["status"] in statuses and f["valid_from"] <= t < f["valid_to"]:
                text = fact_text(f["entity_name"], f["predicate"], f["value"])
                s = keyword_score(qwords, text)
                if s > 0:
                    scored.append((1.0 - s, f["id"], f, text))
        scored.sort(key=lambda x: (x[0], x[1]))
        hits = [
            {
                "fact_id": f["id"],
                "text": text,
                "entity": f["entity_name"],
                "predicate": f["predicate"],
                "value": f["value"],
                "status": f["status"],
                "score": score,
            }
            for score, _, f, text in scored[:k]
        ]
        self._log(agent_id, "recall", query=query, scope=scope, returned=[h["fact_id"] for h in hits])
        return hits

    def forget_source(self, source_id: str) -> dict[str, Any]:
        t = now_ms()
        with self._mem_lock.hold():
            if source_id not in self._load_sources():
                raise UnknownReference(f"no source with id '{source_id}'")
            facts = self._load_facts()
            reached: set[str] = set()
            frontier = {source_id}
            for _ in range(5):
                nxt = {f["id"] for f in facts if f["id"] not in reached and frontier & set(f["derived_from"])}
                if not nxt:
                    break
                reached |= nxt
                frontier = nxt
            ids = sorted(f["id"] for f in facts if f["id"] in reached and f["status"] != "forgotten")
            for f in facts:
                if f["id"] in ids:
                    f["status"], f["valid_to"] = "forgotten", min(f["valid_to"], t)
            self._save_facts(facts)
        self._append(
            self.dir / "decisions.jsonl",
            _dump({"type": "forget", "source_id": source_id, "fact_ids": ids, "at": t}),
        )
        return {"source_id": source_id, "fact_ids": ids}

    def facts(self, subject: str, predicate: str, scope: str = "global") -> list[dict[str, Any]]:
        entity, pred = normalize(subject), normalize(predicate)
        with self._mem_lock.hold():
            facts = self._load_facts()
        rows = sorted(
            (f for f in facts if f["entity"] == entity and f["predicate"] == pred and f["scope"] == scope),
            key=lambda f: (f["valid_from"], f["id"]),
        )
        return [
            {
                "fact_id": f["id"],
                "value": f["value"],
                "status": f["status"],
                "valid_from": f["valid_from"],
                "valid_to": f["valid_to"],
                "asserted_by": list(f["asserted_by"]),
                "supersedes": sorted(f["supersedes"]),
                "contradicts": sorted(f["contradicts"]),
            }
            for f in rows
        ]

    def as_of(self, subject: str, predicate: str, t: int, scope: str = "global") -> dict[str, Any] | None:
        chain = scope_chain(scope)
        entity, pred = normalize(subject), normalize(predicate)
        with self._mem_lock.hold():
            facts = self._load_facts()
        rows = [
            f
            for f in facts
            if f["entity"] == entity
            and f["predicate"] == pred
            and f["scope"] in chain
            and f["status"] in ("active", "superseded")
            and f["valid_from"] <= t < f["valid_to"]
        ]
        if not rows:
            return None
        rows.sort(key=lambda f: (0 if f["scope"] == scope else 1, -f["valid_from"], f["id"]))

        def one(f: dict[str, Any]) -> dict[str, Any]:
            return {k: f[k] for k in ("value", "status", "valid_from", "valid_to")} | {"fact_id": f["id"]}

        best = one(rows[0])
        best["also_valid"] = [one(f) for f in rows[1:20]]
        return best

    # -- coordination -------------------------------------------------------------------------------------------
    def create_tasks(self, tasks: Sequence[dict[str, Any]]) -> list[str]:
        if not tasks:
            return []
        ids = [str(t.get("id") or new_id()) for t in tasks]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate task id in batch")
        t0 = now_ms()
        with self._tasks_lock.hold():
            data = self._load_tasks()
            existing = [i for i in ids if i in data["tasks"]]
            if existing:
                raise ValueError(f"task id(s) already exist: {', '.join(existing)}")
            known = set(ids) | set(data["tasks"])
            missing = sorted(
                {str(d) for t in tasks for d in (t.get("depends_on") or ()) if str(d) not in known}
            )
            if missing:
                raise UnknownReference(f"unknown dependency task id(s): {', '.join(missing)}")
            for tid, t in zip(ids, tasks, strict=True):
                data["tasks"][tid] = {
                    "id": tid,
                    "title": str(t["title"]),
                    "priority": int(t.get("priority", 0)),
                    "seq": data["next_seq"],
                    "status": "open",
                    "claimed_by": "",
                    "lease_until": 0,
                    "version": 0,
                    "created_at": t0,
                    "done_at": 0,
                    "deps": list(dict.fromkeys(str(d) for d in (t.get("depends_on") or ()))),
                    "artifacts": [],
                }
                data["next_seq"] += 1
            self._save_tasks(data)
        return ids

    def claim_next_task(
        self, agent_id: str, lease_ms: int = 60_000, now: int | None = None
    ) -> dict[str, Any] | None:
        if lease_ms <= 0:
            raise ValueError("lease_ms must be positive")
        if not self._agent_exists(agent_id):
            raise UnknownReference(f"unknown agent id(s): {agent_id}")
        t = now if now is not None else now_ms()
        with self._tasks_lock.hold():
            data = self._load_tasks()
            tasks = data["tasks"]
            best = None
            for task in tasks.values():
                if not (
                    task["status"] == "open" or (task["status"] == "claimed" and task["lease_until"] < t)
                ):
                    continue
                if any(tasks[d]["status"] != "done" for d in task["deps"]):
                    continue
                key = (-task["priority"], task["seq"], task["id"])
                if best is None or key < best[0]:
                    best = (key, task)
            if best is None:
                return None
            task = best[1]
            previous = task["claimed_by"]
            task["status"], task["claimed_by"] = "claimed", agent_id
            task["lease_until"], task["version"] = t + lease_ms, task["version"] + 1
            self._save_tasks(data)
        out = {
            "id": task["id"],
            "title": task["title"],
            "priority": task["priority"],
            "version": task["version"],
            "lease_until": task["lease_until"],
            "reclaimed_from": previous,
        }
        self._log(
            agent_id, "claim_next_task", task=task["id"], version=task["version"], reclaimed_from=previous
        )
        return out

    def heartbeat(self, agent_id: str, task_id: str, lease_ms: int = 60_000, now: int | None = None) -> bool:
        if lease_ms <= 0:
            raise ValueError("lease_ms must be positive")
        t = now if now is not None else now_ms()
        with self._tasks_lock.hold():
            data = self._load_tasks()
            task = data["tasks"].get(task_id)
            if task is None or task["claimed_by"] != agent_id or task["status"] != "claimed":
                return False
            task["lease_until"] = max(task["lease_until"], t + lease_ms)
            self._save_tasks(data)
        return True

    def complete_task(
        self, agent_id: str, task_id: str, expected_version: int, artifacts: Sequence[dict[str, Any]] = ()
    ) -> dict[str, Any]:
        arts = [
            {
                "id": str(a.get("id") or new_id()),
                **{k: str(a.get(k) or "") for k in ("kind", "uri", "hash", "summary")},
            }
            for a in artifacts
        ]
        t = now_ms()
        with self._tasks_lock.hold():
            data = self._load_tasks()
            task = data["tasks"].get(task_id)
            if task is None:
                raise UnknownReference(f"unknown task id(s): {task_id}")
            if task["status"] != "claimed":
                raise ClaimConflict(f"task {task_id}: not claimed (status is {task['status']})")
            if task["claimed_by"] != agent_id:
                raise ClaimConflict(f"task {task_id}: claimed by {task['claimed_by']}, not {agent_id}")
            if task["version"] != expected_version:
                raise ClaimConflict(
                    f"task {task_id}: stale version {expected_version}; current is {task['version']}"
                )
            task["status"], task["done_at"], task["version"] = "done", t, task["version"] + 1
            task["artifacts"].extend({**a, "agent_id": agent_id, "created_at": t} for a in arts)
            self._save_tasks(data)
        self._log(agent_id, "complete_task", task=task_id, artifacts=[a["id"] for a in arts])
        return {
            "id": task_id,
            "status": "done",
            "version": expected_version + 1,
            "artifact_ids": [a["id"] for a in arts],
        }

    def _require_refs(
        self, agents: Sequence[str], task_id: str, artifact_ids: Sequence[str], fact_ids: Sequence[str]
    ) -> None:
        for a in dict.fromkeys(agents):
            if not self._agent_exists(a):
                raise UnknownReference(f"unknown agent id(s): {a}")
        with self._tasks_lock.hold():
            data = self._load_tasks()
        if task_id not in data["tasks"]:
            raise UnknownReference(f"unknown task id(s): {task_id}")
        have_art = {a["id"] for t in data["tasks"].values() for a in t["artifacts"]}
        missing = [a for a in artifact_ids if a not in have_art]
        if missing:
            raise UnknownReference(f"unknown artifact id(s): {', '.join(missing)}")
        if fact_ids:
            with self._mem_lock.hold():
                have = {f["id"] for f in self._load_facts()}
            missing = [f for f in fact_ids if f not in have]
            if missing:
                raise UnknownReference(f"unknown fact id(s): {', '.join(missing)}")

    def handoff(
        self,
        agent_id: str,
        to_agent: str,
        task_id: str,
        note: str,
        artifact_ids: Iterable[str] = (),
        fact_ids: Iterable[str] = (),
    ) -> str:
        arts, facts = list(dict.fromkeys(artifact_ids)), list(dict.fromkeys(fact_ids))
        self._require_refs([agent_id, to_agent], task_id, arts, facts)
        hid = new_id()
        rec = {
            "id": hid,
            "from": agent_id,
            "to": to_agent,
            "task": task_id,
            "note": note,
            "artifacts": arts,
            "facts": facts,
            "at": now_ms(),
        }
        self._append(self.dir / "handoffs.jsonl", _dump(rec))
        self._log(agent_id, "handoff", **{k: v for k, v in rec.items() if k != "from"})
        return hid

    def record_decision(
        self, agent_id: str, task_id: str, text: str, based_on_fact_ids: Iterable[str] = ()
    ) -> str:
        facts = list(dict.fromkeys(based_on_fact_ids))
        if len(facts) > 100:
            raise ValueError("at most 100 referenced ids")
        self._require_refs([agent_id], task_id, [], facts)
        did = new_id()
        rec = {
            "type": "decision",
            "id": did,
            "agent": agent_id,
            "task": task_id,
            "text": text,
            "based_on": facts,
            "at": now_ms(),
        }
        self._append(self.dir / "decisions.jsonl", _dump(rec))
        self._log(agent_id, "record_decision", id=did, task=task_id, based_on=facts)
        return did

    def task_status(self, task_id: str) -> dict[str, Any] | None:
        with self._tasks_lock.hold():
            data = self._load_tasks()
        task = data["tasks"].get(task_id)
        if task is None:
            return None
        return {
            "id": task["id"],
            "title": task["title"],
            "status": task["status"],
            "claimed_by": task["claimed_by"],
            "version": task["version"],
            "lease_until": task["lease_until"],
            "dependencies": [{"id": d, "status": data["tasks"][d]["status"]} for d in sorted(task["deps"])],
        }

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._tasks_lock.hold():
            data = self._load_tasks()
        rows = sorted(data["tasks"].values(), key=lambda t: (t["seq"], t["id"]))
        return [{k: t[k] for k in ("id", "status", "claimed_by", "version", "lease_until")} for t in rows]

    # -- lineage -----------------------------------------------------------------------------------------------------
    def why(self, node_id: str) -> dict[str, Any]:
        raise Unsupported(
            "why: decisions.jsonl lists fact ids but nothing links them to who asserted them or where they came from; Layer 2 has an LLM read the files"
        )

    def knew_at(self, agent_id: str, step_n: int) -> dict[str, Any]:
        raise Unsupported(
            "knew_at: per-agent logs are transcripts, not queryable by step; Layer 2 has an LLM read them"
        )
