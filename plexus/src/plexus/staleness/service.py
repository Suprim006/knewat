"""Staleness service: wrappers around the named queries in ``queries/staleness/``.

A code change never makes a fact false, it makes it *suspect* (``verify_state = 'suspect'``); an agent
re-checks it and calls :meth:`Staleness.verify_fact`. Every write is ONE bounded Cypher statement; reads use
``ro``. Time is epoch ms (``clock`` / ``now`` are injectable for tests). No LLM anywhere.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Callable, Sequence
from typing import Any

from redis.exceptions import RedisError

from plexus.activation import Activation, Settings
from plexus.codescan.paths import anchor_id, canonical_path
from plexus.common import OPEN, check_between, normalize, now_ms
from plexus.engram import Engram
from plexus.graph.client import GraphClient
from plexus.lineage import Lineage

KINDS = ("file", "function", "class")
MAX_CHANGES = 200  # entries per mark_changed call (bounds the UNWIND of the write)
MAX_AFFECTED = 2000  # facts made suspect per mark_changed call
MAX_LIST = 200  # facts_to_verify / docs_to_update rows
SCAN_CAP = 5000  # suspect ids read before ranking
DEFAULT_DETAIL = 50  # decisions listed per call (the total is exact)
MAX_DETAIL = 5000  # largest max_detail a caller may ask for
MAX_FLAGGED = 1000  # decisions flagged by one verify_fact
MAX_EVIDENCE = 500  # evidence text kept on the VERIFIED_BY edge
_URL = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://\S+$")
_CODE_EXT = frozenset(
    ".py .pyi .js .jsx .ts .tsx .mjs .go .rs .java .kt .cs .c .h .cpp .hpp .rb .php .swift .sql .sh .ps1 "
    ".yaml .yml .toml .json .ini .cfg .env .dockerfile".split()
)


def _change_id(commit: str, t: int, rows: Sequence[dict[str, Any]]) -> str:
    """Deterministic ``Change`` id: the same commit, time and anchor hashes give the same id (idempotent)."""
    parts = [commit, str(t), *sorted(f"{e['anchor_id']}={e['new_hash']}" for e in rows)]
    return "chg:" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]  # noqa: S324


class Staleness:
    """Staleness operations bound to one tenant graph."""

    def __init__(
        self,
        client: GraphClient,
        graph: str,
        *,
        engram: Engram | None = None,
        clock: Callable[[], int] = now_ms,
        rank: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
        forgetting: bool | None = None,
    ):
        self.client = client
        self.graph = graph
        self._engram = engram
        self._clock = clock
        self._rank = rank  # replaces the default ordering when given
        self._forgetting = forgetting  # None = PLEXUS_FORGETTING (default on)

    def _t(self, now: int | None) -> int:
        return self._clock() if now is None else int(now)

    # -- anchors and descriptions ---------------------------------------------------------------------
    def _upsert_anchor(
        self,
        path: str,
        symbol: str,
        hash: str,
        kind: str,
        repo: str,
        *,
        fact_id: str = "",
        source_id: str = "",
        now: int | None,
    ) -> dict[str, Any] | None:
        cpath = canonical_path(path)
        symbol = symbol.strip()
        kind = kind or ("function" if symbol else "file")
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        if (kind == "file") != (symbol == ""):
            raise ValueError("a file anchor has no symbol; a function / class anchor needs one")
        rows = self.client.rw(
            self.graph,
            "staleness/upsert_anchor",
            {
                "anchor_id": anchor_id(cpath, symbol),
                "repo": repo,
                "path": cpath,
                "symbol": symbol,
                "kind": kind,
                "hash": hash,
                "fact_id": fact_id,
                "source_id": source_id,
                "now": self._t(now),
            },
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "anchor_id": r["anchor_id"],
            "path": cpath,
            "symbol": symbol,
            "kind": kind,
            "hash": r["hash"],
            "created": bool(r["created"]),
        }

    def anchor_fact(
        self,
        fact_id: str,
        path: str,
        symbol: str = "",
        hash: str = "",
        *,
        kind: str = "",
        repo: str = "",
        now: int | None = None,
    ) -> dict[str, Any]:
        """Link a Fact to a file (``symbol=''``) or a Python function / class (``ANCHORED_TO`` a CodeAnchor).

        ``path`` is normalised to the canonical form (absolute, ``/``, upper-case drive). ``hash`` is the code
        hash the fact was verified against; it is stored only when the anchor has none yet. Raises
        :class:`LookupError` (nothing written) for an unknown fact, :class:`ValueError` for a bad path / kind.
        """
        out = self._upsert_anchor(path, symbol, hash, kind, repo, fact_id=fact_id, now=now)
        if out is None:
            raise LookupError(f"no fact with id '{fact_id}'")
        return {"fact_id": fact_id, **out}

    def describe_code(
        self,
        source_id: str,
        path: str,
        symbol: str = "",
        hash: str = "",
        *,
        kind: str = "",
        repo: str = "",
        now: int | None = None,
    ) -> dict[str, Any]:
        """Record that a doc Source describes a file / function: ``(Source)-[:DESCRIBES]->(CodeAnchor)``.

        When the code changes, :meth:`docs_to_update` lists the doc. Raises :class:`LookupError` for an
        unknown source (nothing written).
        """
        out = self._upsert_anchor(path, symbol, hash, kind, repo, source_id=source_id, now=now)
        if out is None:
            raise LookupError(f"no source with id '{source_id}'")
        return {"source_id": source_id, **out}

    # -- changes --------------------------------------------------------------------------------------
    def mark_changed(
        self,
        changes: Sequence[dict[str, Any]],
        commit: str = "",
        at: int | None = None,
        agent_id: str = "code-hook",
        *,
        limit: int = MAX_AFFECTED,
        max_detail: int = DEFAULT_DETAIL,
        repo: str = "",
        now: int | None = None,
    ) -> dict[str, Any]:
        """Record code changes; active and dormant facts that depend on a changed file or symbol turn suspect.

        ``changes`` is ``[{path, symbol='', new_hash, old_hash='', kind?}]`` (at most 200). An entry is
        *changed* when the hash stored for its anchor (or, when none is stored yet, ``old_hash``) differs from
        ``new_hash``; a first sighting without ``old_hash`` is a baseline and marks nothing. ``new_hash=''``
        means the file / symbol is gone. A file-level change covers the symbol anchors of that file only when
        the batch has no symbol entries for it. Affected facts: those ``ANCHORED_TO`` a changed anchor, plus
        those ``DERIVED_FROM*1..5`` a ``Source`` whose uri is the changed (canonical) path.
        Dormant facts (moved by a sweep) are marked too, so restoring one brings it back suspect; they are not
        listed in ``suspect_fact_ids``, which names the active ones. Returns ``{change_id, at, changed,
        unchanged, suspect_fact_ids, decisions, decisions_total,
        docs_to_update, truncated}``. ``change_id`` is ``None`` when nothing changed (no Change is created).

        At most ``limit`` (<= 2000) facts are marked per call. When more are affected ``truncated`` is true
        and the hashes are not advanced: call again with the same arguments (including the returned ``at``) to
        continue with the same Change.
        """
        check_between("limit", limit, MAX_AFFECTED)
        check_between("max_detail", max_detail, MAX_DETAIL)
        if len(changes) > MAX_CHANGES:
            raise ValueError(f"at most {MAX_CHANGES} changes per call")
        if not changes:
            raise ValueError("changes must not be empty")
        rows = self._change_entries(changes, repo)
        t = self._t(at)
        res = self.client.rw(
            self.graph,
            "staleness/mark_changed",
            {
                "changes": rows,
                "paths": sorted({e["path"] for e in rows}),
                "change_id": _change_id(commit, t, rows),
                "commit": commit,
                "at": t,
                "now": self._t(now),
                "agent_id": agent_id,
                "limit": limit,
                "limit_plus": limit + 1,
                "max_detail": max_detail,
            },
        )
        r = res[0]
        return {
            "change_id": r["change_id"],
            "at": t,
            "changed": r["changed"],
            "unchanged": len(rows) - r["changed"],
            "suspect_fact_ids": list(r["fact_ids"]),
            "decisions": [dict(d) for d in r["decisions"]],
            "decisions_total": r["decisions_total"],
            "docs_to_update": sorted((dict(d) for d in r["docs"]), key=lambda d: (d["uri"], d["anchor"])),
            "truncated": bool(r["truncated"]),
        }

    @staticmethod
    def _change_entries(changes: Sequence[dict[str, Any]], repo: str) -> list[dict[str, Any]]:
        """One row per anchor for the ``staleness/mark_changed`` UNWIND (the last entry for an anchor wins).

        ``cover`` marks a file-level entry that also covers the symbol anchors of its file, which only
        happens when the batch has no symbol entries for that file.
        """
        entries: dict[str, dict[str, Any]] = {}
        for ch in changes:
            cpath = canonical_path(ch["path"])
            symbol = (ch.get("symbol") or "").strip()
            kind = ch.get("kind") or ("function" if symbol else "file")
            if kind not in KINDS or (kind == "file") != (symbol == ""):
                raise ValueError(f"bad kind '{kind}' for symbol '{symbol}'")
            aid = anchor_id(cpath, symbol)
            entries[aid] = {
                "anchor_id": aid,
                "path": cpath,
                "symbol": symbol,
                "kind": kind,
                "repo": ch.get("repo") or repo,
                "new_hash": ch.get("new_hash") or "",
                "old_hash": ch.get("old_hash") or "",
                "cover": False,
            }
        with_symbols = {e["path"] for e in entries.values() if e["symbol"]}
        for e in entries.values():
            e["cover"] = e["kind"] == "file" and e["path"] not in with_symbols
        return list(entries.values())

    # -- verification ---------------------------------------------------------------------------------
    def verify_fact(
        self,
        fact_id: str,
        still_true: bool,
        new_value: str = "",
        evidence: str = "",
        agent_id: str = "agent",
        commit: str = "",
        *,
        now: int | None = None,
    ) -> dict[str, Any]:
        """An agent re-checked a (suspect) fact; Plexus records the outcome.

        ``still_true``: the fact becomes ``verified`` (``verified_at`` = now, ``VERIFIED_BY {outcome:
        'confirmed'}``; fine on a fact that is not suspect, it refreshes ``verified_at``). A review date
        (``verify_after``) that has passed is consumed.

        Not true any more: ``new_value`` is required (``ValueError`` otherwise, nothing written).
        The backdate point is READ first (``staleness/backdate_point``: a failing read writes
        nothing); then the existing supersede path creates the new fact (``Engram.assert_fact(...,
        supersede=True)``); then ONE statement (``staleness/backdate``) puts the old fact's
        ``valid_to`` and the new fact's ``valid_from`` at the time of the newest ``Change`` that
        suspected the old fact and is newer than its last confirmation (event time; ``recorded_at``
        stays the time Plexus learned the value), marks the old fact verified, adds ``VERIFIED_BY
        {outcome:'changed'}`` and flags the Decisions ``BASED_ON`` the old fact (``flag_reason =
        'fact changed: <id>'``).

        The supersede and the backdate are not atomic together (FalkorDB has no multi-statement
        transaction): a failed backdate is retried once; if that fails too the new value is still
        recorded, the old fact gets ``verify_degraded = true`` and the result carries
        ``verify_degraded: True`` (``valid_to`` then is the supersede time and no decisions are
        flagged). Calling ``verify_fact`` again on the old fact with the same ``new_value`` finishes
        the job.

        ``evidence`` that is an absolute path or URL becomes (or reuses) a ``Source`` the new fact
        is ``DERIVED_FROM``; any other text is kept on the edge. A new value equal to the old one
        counts as confirmed. Only a current (``active``) fact can be changed.

        Returns ``{fact_id, outcome, flagged_decisions, new_fact_id?, valid_to?, verify_degraded?}``. Raises
        :class:`LookupError` (unknown fact) and :class:`ValueError`.
        """
        t = self._t(now)
        if not still_true and not normalize(new_value):
            raise ValueError("new_value is required when the fact is no longer true")
        rows = self.client.ro(self.graph, "staleness/fact_for_verify", {"fact_id": fact_id})
        if not rows:
            raise LookupError(f"no fact with id '{fact_id}'")
        old = rows[0]
        note = evidence.strip()
        if still_true or normalize(new_value) == old["norm_value"]:
            return self._confirm_fact(fact_id, agent_id, commit, note, t)
        if old["status"] != "active":
            if old["verify_degraded"] and old["successors"]:
                return self._finish_degraded(old, fact_id, new_value, agent_id, commit, note, t)
            raise ValueError(
                f"fact '{fact_id}' is {old['status']}, not current: verify the fact that replaced it"
            )
        return self._replace_fact(old, fact_id, new_value, agent_id, commit, note, t)

    def _confirm_fact(self, fact_id: str, agent_id: str, commit: str, note: str, t: int) -> dict[str, Any]:
        """``VERIFIED_BY {outcome: 'confirmed'}``: the fact is still true; ``verified_at`` is refreshed."""
        self.client.rw(
            self.graph,
            "staleness/verify_confirm",
            {
                "fact_id": fact_id,
                "agent_id": agent_id,
                "commit": commit,
                "evidence": note[:MAX_EVIDENCE],
                "now": t,
                "open_to": OPEN,
            },
        )
        return {"fact_id": fact_id, "outcome": "confirmed", "flagged_decisions": []}

    def _change_point(self, fact_id: str, t: int) -> int:
        """The event time the old fact's window may end at (``-1`` = none); a read, so it runs first."""
        rows = self.client.ro(self.graph, "staleness/backdate_point", {"old_id": fact_id, "now": t})
        return int(rows[0]["change_at"]) if rows else -1

    def _backdate(
        self,
        old_id: str,
        new_id: str,
        backdate: bool,
        change_at: int,
        agent_id: str,
        commit: str,
        note: str,
        t: int,
    ) -> dict[str, Any] | None:
        """Run ``staleness/backdate``; one retry after a connection / server error. ``None`` = both failed."""
        params = {
            "old_id": old_id,
            "new_id": new_id,
            "backdate": backdate,
            "change_at": change_at,
            "agent_id": agent_id,
            "commit": commit,
            "evidence": note[:MAX_EVIDENCE],
            "now": t,
            "reason": f"fact changed: {old_id}",
            "max_flag": MAX_FLAGGED,
        }
        for _attempt in range(2):
            try:
                rows = self.client.rw(self.graph, "staleness/backdate", params)
            except (RedisError, OSError):
                continue
            return rows[0]
        return None

    def _replace_fact(
        self,
        old: dict[str, Any],
        fact_id: str,
        new_value: str,
        agent_id: str,
        commit: str,
        note: str,
        t: int,
    ) -> dict[str, Any]:
        """Supersede ``old`` with ``new_value`` (Engram), then backdate and flag in one statement.

        Ordered so that a failure leaves a state that can be found and finished: the backdate point is READ
        first (a failing read writes nothing), then the supersede, then the backdate, retried once. If both
        attempts fail the old fact gets ``verify_degraded = true`` and the result says so.
        """
        source_id = self._evidence_source(note, t)
        change_at = self._change_point(fact_id, t)
        r = self._engram_().assert_fact(
            old["subject"],
            old["predicate"],
            new_value,
            old["scope_id"],
            agent_id,
            source_id=source_id,
            now=t,
            supersede=True,
            subject_kind=old["subject_kind"] or "thing",
            dup_threshold=-1.0,  # a corrected value is never a paraphrase of the old one (real run)
        )
        new_id = r["fact_id"]
        b = self._backdate(
            fact_id,
            new_id,
            r["duplicate_of"] is None and r["superseded"] == [fact_id],
            change_at,
            agent_id,
            commit,
            note,
            t,
        )
        if b is None:
            return self._degraded(fact_id, new_id, max(t, old["valid_from"]))
        return {
            "fact_id": fact_id,
            "outcome": "changed",
            "new_fact_id": new_id,
            "valid_to": b["valid_to"],
            "flagged_decisions": sorted(b["decision_ids"]),
        }

    def _degraded(self, fact_id: str, new_id: str, valid_to: int) -> dict[str, Any]:
        """The supersede happened but the backdate did not: flag the old fact so the gap can be found."""
        try:
            self.client.rw(self.graph, "staleness/mark_degraded", {"fact_id": fact_id})
        except (RedisError, OSError) as exc:  # the database is gone: nothing more can be recorded
            raise RuntimeError(
                f"fact '{fact_id}' was superseded by '{new_id}' but the verification could not be completed "
                "or flagged; call verify_fact again with the same new_value"
            ) from exc
        return {
            "fact_id": fact_id,
            "outcome": "changed",
            "new_fact_id": new_id,
            "valid_to": valid_to,
            "flagged_decisions": [],
            "verify_degraded": True,
        }

    def _finish_degraded(
        self,
        old: dict[str, Any],
        fact_id: str,
        new_value: str,
        agent_id: str,
        commit: str,
        note: str,
        t: int,
    ) -> dict[str, Any]:
        """Finish a verification that superseded the fact but could not backdate it (``verify_degraded``)."""
        succ = next((s for s in old["successors"] if s["norm_value"] == normalize(new_value)), None)
        if succ is None:
            shown = ", ".join(f"'{s['norm_value']}'" for s in old["successors"])
            raise ValueError(
                f"fact '{fact_id}' was already replaced by {shown} (its verification is unfinished): "
                "call verify_fact again with that value"
            )
        change_at = self._change_point(fact_id, t)
        b = self._backdate(fact_id, succ["id"], True, change_at, agent_id, commit, note, t)
        if b is None:
            raise RuntimeError(f"could not finish the verification of fact '{fact_id}': the database refused")
        return {
            "fact_id": fact_id,
            "outcome": "changed",
            "new_fact_id": succ["id"],
            "valid_to": b["valid_to"],
            "flagged_decisions": sorted(b["decision_ids"]),
        }

    def _engram_(self) -> Engram:
        if self._engram is None:
            self._engram = Engram(self.client, self.graph)
        return self._engram

    def _evidence_source(self, evidence: str, now: int) -> str | None:
        """The Source for ``evidence`` when it is an absolute path or a URL, else ``None``."""
        if not evidence:
            return None
        if _URL.match(evidence):
            uri, kind = evidence, "external"
        else:
            try:
                uri = canonical_path(evidence)
            except ValueError:
                return None
            kind = "code" if "." + uri.rsplit(".", 1)[-1].lower() in _CODE_EXT else "doc"
        hit = self.client.ro(self.graph, "staleness/source_by_uri", {"uri": uri})
        if hit:
            return hit[0]["id"]
        return Lineage(self.client, self.graph, clock=self._clock).create_source(uri, kind, now=now)

    # -- review dates and work lists ------------------------------------------------------------------
    def set_review_date(self, fact_id: str, verify_after: int) -> dict[str, Any]:
        """Give a fact (not about code) a review date (epoch ms); once passed the fact is due for re-checking.

        ``OPEN`` (9999999999999) clears it. Raises :class:`LookupError` for an unknown fact.
        """
        if not 0 <= verify_after <= OPEN:
            raise ValueError(f"verify_after must be an epoch-ms time between 0 and {OPEN}")
        rows = self.client.rw(
            self.graph, "staleness/set_review_date", {"fact_id": fact_id, "verify_after": int(verify_after)}
        )
        if not rows:
            raise LookupError(f"no fact with id '{fact_id}'")
        return {"fact_id": fact_id, "verify_after": rows[0]["verify_after"]}

    def facts_to_verify(
        self, scope_id: str = "", limit: int = 50, *, now: int | None = None
    ) -> list[dict[str, Any]]:
        """Active facts that are suspect now (changed code, or a review date that has passed).

        Rule (contract): ``verify_state = 'suspect'`` OR ``verify_after <= now``. ``scope_id`` limits the rows
        to a scope and the scopes it inherits (``''`` = all). Each row: ``{fact_id, entity, predicate, value,
        scope_id, verify_state, suspect_since, verify_after, reason, decisions_count, anchors, change}``.
        ``reason`` is ``'changed in <commit or working tree> (<first path>)'`` or ``'review date passed'``.
        Ordered by ``decisions_count`` DESC (non-flagged decisions on it), then ``activation`` DESC
        (D-012: the fact people actually use first), then ``suspect_since`` ASC. With forgetting on each row
        also carries ``activation`` (float, ``None`` without usable events) and ``protected``; with forgetting
        off the rows have neither and the order is ``decisions_count`` DESC, ``suspect_since`` ASC. Reading
        the list does not strengthen the facts. An optional ``rank`` callable given to the constructor
        replaces the ordering.
        """
        check_between("limit", limit, MAX_LIST)
        t = self._t(now)
        ids = [
            r["id"] for r in self.client.ro(self.graph, "staleness/suspect_ids", {"now": t, "cap": SCAN_CAP})
        ]
        if not ids:
            return []
        rows = self.client.ro(
            self.graph,
            "staleness/facts_to_verify",
            {"ids": ids, "scope_id": scope_id, "open_to": OPEN, "limit": SCAN_CAP},
        )
        out: list[dict[str, Any]] = []
        for r in rows:
            change = None
            if r["change_id"] is not None:
                change = {
                    "change_id": r["change_id"],
                    "commit": r["change_commit"],
                    "at": r["change_at"],
                    "paths": json.loads(r["change_paths"] or "[]"),
                }
            if r["verify_state"] == "suspect" and change is not None:
                first = change["paths"][0] if change["paths"] else "?"
                reason = f"changed in {change['commit'] or 'working tree'} ({first})"
            elif r["verify_state"] == "suspect":
                reason = "marked suspect"
            else:
                reason = "review date passed"
            out.append(
                {
                    "fact_id": r["fact_id"],
                    "entity": r["entity"],
                    "predicate": r["predicate"],
                    "value": r["value"],
                    "scope_id": r["scope_id"],
                    "verify_state": r["verify_state"],
                    "suspect_since": r["suspect_since"],
                    "verify_after": r["verify_after"],
                    "reason": reason,
                    "decisions_count": r["decisions_count"],
                    "anchors": list(dict.fromkeys(r["anchors"])),
                    "change": change,
                }
            )
        if self._rank is not None:
            out = self._rank(out)
        elif self._use_activation():
            out = self._order_by_activation(out, t)
        return out[:limit]

    def _use_activation(self) -> bool:
        if self._forgetting is not None:
            return self._forgetting
        return Settings.from_env().forgetting

    def _order_by_activation(self, rows: list[dict[str, Any]], now: int) -> list[dict[str, Any]]:
        """Add ``activation`` / ``protected`` to the rows and order them (decisions, activation, age)."""
        act = Activation(self.client, self.graph, clock=self._clock).compute(
            [r["fact_id"] for r in rows], now
        )
        for r in rows:
            fa = act.get(r["fact_id"])
            finite = fa is not None and math.isfinite(fa.activation)
            r["activation"] = float(fa.activation) if fa is not None and finite else None
            r["protected"] = bool(fa.protected) if fa is not None else False
        floor = float("-inf")
        return sorted(
            rows,
            key=lambda r: (
                -r["decisions_count"],
                -(r["activation"] if r["activation"] is not None else floor),
                r["suspect_since"],
                r["fact_id"],
            ),
        )

    def docs_to_update(self, since: int = 0, limit: int = 50, *, per_doc: int = 10) -> list[dict[str, Any]]:
        """Doc Sources that ``DESCRIBES`` code touched by a Change at or after ``since``, not edited since.

        Each row: ``{source_id, uri, title, latest, changes: [{change_id, commit, at, paths, anchor}]}``,
        newest change first. A doc whose own file was reported to ``mark_changed`` after the code change drops
        off the list.
        """
        check_between("limit", limit, MAX_LIST)
        rows = self.client.ro(
            self.graph,
            "staleness/docs_to_update",
            {"since": int(since), "limit": limit, "per_doc": max(1, min(per_doc, 50))},
        )
        return [
            {
                "source_id": r["source_id"],
                "uri": r["uri"],
                "title": r["title"],
                "latest": r["latest"],
                "changes": [{**c, "paths": json.loads(c["paths"] or "[]")} for c in r["changes"]],
            }
            for r in rows
        ]
