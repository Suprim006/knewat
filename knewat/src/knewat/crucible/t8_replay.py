"""$0 replay of trial 8 (provenance + retraction of a void source) against the multi-source build (P13).

    python -m plexus.crucible.t8_replay [--port 6377] [--out plexus/demo_data/crucible/t8replay]

Trial 8 (``trials/FINDINGS.md`` section 5): session 1 registers a compliance memo (rules C1, C2, C3) and a product
spec (P1, P2; P2 is the same rule as C1), session 3 says "the memo is void: remove the rules that came only from
it". Right answer: C2 and C3 go; C1 (the spec still requires it) and P1 stay. The four Plexus runs linked C1 to the
memo only (``assert_fact`` took one ``source_id``) and never called ``quarantine_source``.

This script replays that through the real MCP tools (in-memory client, no model, no cost), three ways, each on its
own throwaway tenant:

* ``source_ids``    session 1 as the new description asks: C1 written with ``source_ids=[memo, spec]``.
* ``corroboration`` session 1 as the runs wrote it, plus the spec's P2 asserted with the same wording: the duplicate
                    assert links the spec to C1 (``sources_added``).
* ``single_source`` control, exactly what the four runs wrote (C1 -> memo only, "also P2" in the text): the engine
                    can only hide C1, because the graph says nothing else supports it.

Per scenario: ``quarantine_source(memo)``, ``release_quarantine(memo)``, ``forget_source(memo)``; after each step the
status of every rule, what ``recall`` returns, and the sources ``why`` lists for C1. Writes ``results.json`` and
``results.md`` into ``--out``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from mcp import Client
from plexus.embed import HashEmbedder
from plexus.graph.client import GraphClient
from plexus.graph.queries import QueryLibrary
from plexus.graph.tenancy import graph_name
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_server

RULES = ("C1", "C2", "C3", "P1")
C1_TEXT = "export outputs active tasks only; archived tasks are never exported"
MEMO_TEXT = (
    "C1 export omits archived; C2 add replaces emails in title with [email]; C3 reschedule rejects past due date. "
    "Status: DRAFT."
)
SPEC_TEXT = "P1 tag stores lowercase; P2 export outputs active tasks only."
DEFAULT_OUT = Path(__file__).resolve().parents[3] / "demo_data" / "crucible" / "t8replay"


async def _call(c: Client, name: str, **args: Any) -> dict[str, Any]:
    res = await c.call_tool(name, {"agent_id": "builder-1", **args})
    if res.is_error:
        raise RuntimeError(f"{name}: {res.content[0].text}")  # type: ignore[union-attr]
    return json.loads(res.content[0].text)  # type: ignore[union-attr]


async def _session1(c: Client, scenario: str) -> dict[str, Any]:
    memo = (
        await _call(c, "add_source", title="Compliance memo DRAFT v0.3", uri="urn:t8:memo", text=MEMO_TEXT)
    )["source_id"]
    spec = (
        await _call(
            c, "add_source", title="Product spec v2 - tinytasks CLI", uri="urn:t8:spec", text=SPEC_TEXT
        )
    )["source_id"]
    ids: dict[str, str] = {}

    async def rule(name: str, subject: str, predicate: str, value: str, **src: Any) -> dict[str, Any]:
        r = await _call(c, "assert_fact", subject=subject, predicate=predicate, value=value, **src)
        ids.setdefault(name, r["fact_id"])
        return r

    notes: dict[str, Any] = {}
    if scenario == "source_ids":
        await rule("C1", "tinytasks export", "archived_tasks_policy", C1_TEXT, source_ids=[memo, spec])
    elif scenario == "corroboration":
        await rule("C1", "tinytasks export", "archived_tasks_policy", C1_TEXT, source_id=memo)
        again = await _call(
            c,
            "assert_fact",
            subject="tinytasks export",
            predicate="archived_tasks_policy",
            value=C1_TEXT,
            source_id=spec,
        )
        notes["second_assert"] = {k: again.get(k) for k in ("duplicate_of", "sources_added")}
        notes["second_assert_same_fact"] = again["fact_id"] == ids["C1"]
    else:  # single_source: what the four trial-8 runs wrote
        await rule(
            "C1",
            "tinytasks export",
            "archived_tasks_policy",
            f"{C1_TEXT} (compliance C1 / product P2)",
            source_id=memo,
        )
    await rule(
        "C2",
        "tinytasks add",
        "email_in_title_policy",
        "emails in a task title are replaced with [email] (compliance C2)",
        source_id=memo,
    )
    await rule(
        "C3",
        "tinytasks reschedule",
        "past_due_date_policy",
        "reschedule rejects a due date in the past (compliance C3)",
        source_id=memo,
    )
    await rule(
        "P1",
        "tinytasks tag",
        "tag_case_policy",
        "tags are case-insensitive; stored in lowercase (product P1)",
        source_id=spec,
    )
    return {"memo": memo, "spec": spec, "ids": ids, "notes": notes}


async def _state(c: Client, rt: Runtime, tenant: str, s: dict[str, Any]) -> dict[str, Any]:
    g = rt.client.graph(graph_name(tenant))
    status = {r[0]: r[1] for r in g.ro_query("MATCH (f:Fact) RETURN f.id, f.status").result_set}
    inv = {fid: name for name, fid in s["ids"].items()}
    recalled = (await _call(c, "recall", query="tinytasks", k=20, scope="all"))["facts"]
    why = (await _call(c, "why", node_id=s["ids"]["C1"]))["why"]
    names = {s["memo"]: "memo", s["spec"]: "spec"}
    c1 = next(f for f in why["facts"] if f["id"] == s["ids"]["C1"])
    return {
        "status": {inv[f]: st for f, st in status.items() if f in inv},
        "recalled": sorted(inv[h["fact_id"]] for h in recalled if h["fact_id"] in inv),
        "c1_sources": sorted(names.get(x, x) for x in c1["sources"]),
    }


def _named(
    items: list[dict[str, Any]], s: dict[str, Any], key: str = "other_sources"
) -> list[dict[str, Any]]:
    inv = {fid: name for name, fid in s["ids"].items()}
    names = {s["memo"]: "memo", s["spec"]: "spec"}
    return [{"fact": inv[i["fact_id"]], key: sorted(names[o] for o in i[key])} for i in items]


async def run_scenario(client: GraphClient, scenario: str) -> dict[str, Any]:
    tenant = f"t8replay_{uuid.uuid4().hex[:10]}"
    rt = Runtime(client=client, embedder=HashEmbedder(), stdio_tenant=tenant)
    try:
        async with Client(build_server(rt)) as c:
            s = await _session1(c, scenario)
            inv = {fid: name for name, fid in s["ids"].items()}
            out: dict[str, Any] = {
                "scenario": scenario,
                "session1": s["notes"],
                "after_session1": await _state(c, rt, tenant, s),
            }
            q = (await _call(c, "quarantine_source", source_id=s["memo"]))["quarantined"]
            out["quarantine_memo"] = {
                "hidden": sorted(inv[f] for f in q["fact_ids"]),
                "corroborated": _named(q.get("corroborated", []), s),
                **await _state(c, rt, tenant, s),
            }
            r = await _call(c, "release_quarantine", source_id=s["memo"])
            out["release_memo"] = {
                "restored": sorted(inv[f] for f in r["released"]["fact_ids"]),
                **await _state(c, rt, tenant, s),
            }
            f = (await _call(c, "forget_source", source_id=s["memo"]))["forgotten"]
            out["forget_memo"] = {
                "forgotten": sorted(inv[x] for x in f["fact_ids"]),
                "unlinked": _named(f.get("unlinked", []), s),
                **await _state(c, rt, tenant, s),
            }
        return out
    finally:
        client.delete_graph(graph_name(tenant))


SCENARIOS = ("source_ids", "corroboration", "single_source")


def render(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Trial 8 replay on the multi-source build ($0, scripted)",
        "",
        "Memo (C1, C2, C3) and spec (P1, P2 = C1's rule). `quarantine_source(memo)` should hide C2 and C3 and keep C1 and P1.",
        "",
        "| scenario | hidden by quarantine(memo) | corroborated (stays visible) | visible after | released | forget(memo): forgotten | unlinked | C1 sources after forget |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        q, rel, f = r["quarantine_memo"], r["release_memo"], r["forget_memo"]
        vis = ", ".join(x for x in RULES if q["status"][x] == "active")
        lines.append(
            f"| {r['scenario']} | {', '.join(q['hidden'])} | {', '.join(x['fact'] + ' (' + '+'.join(x['other_sources']) + ')' for x in q['corroborated']) or '-'} "
            f"| {vis} | {', '.join(rel['restored'])} | {', '.join(f['forgotten'])} "
            f"| {', '.join(x['fact'] for x in f['unlinked']) or '-'} | {', '.join(f['c1_sources']) or '-'} |"
        )
    lines += [
        "",
        "Control (`single_source`) is what the four trial-8 runs wrote: the graph names the memo only, so C1 is hidden.",
        "",
    ]
    return "\n".join(lines)


async def amain(port: int, out_dir: Path) -> list[dict[str, Any]]:
    client = GraphClient(host="127.0.0.1", port=port, password="", library=QueryLibrary())
    try:
        results = [await run_scenario(client, sc) for sc in SCENARIOS]
    finally:
        client.close()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out_dir / "results.md").write_text(render(results), encoding="utf-8")
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=6377)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    print(render(asyncio.run(amain(a.port, a.out))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
