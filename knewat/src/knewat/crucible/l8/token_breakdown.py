"""Where do an L8 arm's tokens go? A per-tool attribution from the recorded ``claude -p`` transcripts. No LLM, $0.

    python -m knewat.crucible.l8.token_breakdown --runs knewat/demo_data/crucible/l8_postfix/runs --arms P,B1,B0p

Model (exact in aggregate, proportional inside one delta):

* One ``claude -p`` process = one transcript. Every distinct assistant ``message.id`` is one API call; its usage
  gives the prompt size ``input + cache_creation + cache_read`` and ``output``.
* The first call's prompt is the **prefix**: Claude Code's system prompt + the tool manifest (built-in tools and
  every MCP tool's name/description/schema) + the harness prompt. It is re-read by every call of the process.
* Between call k-1 and call k the prompt grows by ``delta_k``: the blocks call k-1 emitted (tool_use inputs, text,
  thinking) and the tool results that came back. ``delta_k`` is split across those blocks in proportion to their
  characters, so each block gets a token size that sums exactly to the measured growth.
* A block present from call k on is re-read by every later call of the process, so its **charged** tokens are
  ``size * (number of calls that carry it)``. Output tokens of a call are charged to its blocks by characters too.
* sum(prefix charges) + sum(block charges) + sum(output) == the transcript's total tokens (checked per process).
* A second, coarser view (``round_trip``): every API call after the first exists because tool results came back,
  so its whole prompt + output is charged to the tools whose results it carries (split evenly). That is what one
  more call of a tool costs, prefix re-read included; the first call of a process goes to ``(process start)``.

The recall response is further split by JSON field (``fact_id``, ``text``, ``path``, ``valid_from`` ...), each
field's share of the response characters times the response's charged tokens.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

MCP = "mcp__knewat__"


def _name(n: str) -> str:
    return n[len(MCP) :] if n.startswith(MCP) else n


def _result_text(c: Any) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in c)
    return json.dumps(c)


def parse_process(path: Path) -> dict[str, Any]:
    """Calls in order: [{'prompt': int, 'output': int, 'emitted': [(kind, tool, chars, payload)], 'results': [...]}]."""
    calls: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    tool_of: dict[str, str] = {}
    result_usage: dict[str, int] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        t = d.get("type")
        if t == "assistant":
            m = d["message"]
            c = by_id.get(m["id"])
            if c is None:
                u = m.get("usage") or {}
                c = {"prompt": int(u.get("input_tokens") or 0) + int(u.get("cache_creation_input_tokens") or 0)
                     + int(u.get("cache_read_input_tokens") or 0),
                     "output": int(u.get("output_tokens") or 0), "emitted": [], "results": []}  # fmt: skip
                by_id[m["id"]] = c
                calls.append(c)
            c["output"] = max(c["output"], int((m.get("usage") or {}).get("output_tokens") or 0))
            for b in m.get("content") or []:
                bt = b.get("type")
                if bt == "tool_use":
                    tool_of[b["id"]] = _name(b["name"])
                    c["emitted"].append(
                        ("call", _name(b["name"]), len(json.dumps(b.get("input"))) + len(b["name"]), None)
                    )
                elif bt == "text":
                    c["emitted"].append(("text", "(assistant text)", len(b.get("text", "")), None))
                elif bt == "thinking":
                    c["emitted"].append(("thinking", "(thinking)", len(b.get("thinking", "")) + 1, None))
        elif t == "user" and calls:
            for b in (d.get("message") or {}).get("content") or []:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    txt = _result_text(b.get("content"))
                    calls[-1]["results"].append(
                        ("result", tool_of.get(b.get("tool_use_id"), "?"), len(txt), txt)
                    )
        elif t == "result":
            u = d.get("usage") or {}
            result_usage = {k: int(u.get(k) or 0) for k in
                            ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}  # fmt: skip
    return {"calls": calls, "result_usage": result_usage}


def attribute(proc: dict[str, Any], acc: dict[str, Any]) -> None:
    calls = proc["calls"]
    if not calls:
        return
    n = len(calls)
    acc["api_calls"] += n
    acc["processes"] += 1
    acc["prefix_tokens_first_call"].append(calls[0]["prompt"])
    acc["charged"]["(prefix: system + tool manifest + prompt)"] += calls[0]["prompt"] * n
    acc["size"]["(prefix: system + tool manifest + prompt)"] += calls[0]["prompt"]
    for k in range(n):
        c = calls[k]
        blocks = c["emitted"] + c["results"]
        # output of call k, charged by characters to what it emitted
        em_chars = sum(b[2] for b in c["emitted"]) or 1
        for _kind, tool, ch, _ in c["emitted"]:
            acc["output"][tool] += c["output"] * ch / em_chars
        if not c["emitted"]:
            acc["output"]["(no block)"] += c["output"]
        trig = [b[1] for b in calls[k - 1]["results"]] if k else []
        for tool in trig or ["(process start)" if k == 0 else "(no tool result)"]:
            acc["round_trip"][tool] += (c["prompt"] + c["output"]) / max(1, len(trig))
        if k + 1 >= n:
            continue  # last call: its blocks are never re-read in this process
        delta = calls[k + 1]["prompt"] - c["prompt"]
        tot = sum(b[2] for b in blocks) or 1
        carried = n - (k + 1)  # calls k+1 .. n-1 carry these blocks
        if delta < 0:
            acc["negative_deltas"] += 1
            delta = 0
        for kind, tool, ch, payload in blocks:
            size = delta * ch / tot
            key = f"{tool} [{'response' if kind == 'result' else 'request' if kind == 'call' else kind}]"
            acc["charged"][key] += size * carried
            acc["size"][key] += size
            if kind == "result" and tool == "recall" and payload:
                _recall_fields(payload, size * carried, acc)
            if kind == "result":
                acc["result_chars"][tool] += ch
        # calls: count tool calls once
        for kind, tool, _ch, _ in c["emitted"]:
            if kind == "call":
                acc["calls"][tool] += 1
    for kind, tool, _ch, _ in calls[-1]["emitted"]:
        if kind == "call":
            acc["calls"][tool] += 1
    measured = sum(c["prompt"] + c["output"] for c in calls)
    acc["measured_total"] += measured
    ru = proc["result_usage"]
    if ru:
        acc["result_total"] += sum(ru.values())


def _recall_fields(payload: str, charged: float, acc: dict[str, Any]) -> None:
    try:
        d = json.loads(payload)
    except ValueError:
        return
    total = len(payload) or 1
    sizes: dict[str, int] = defaultdict(int)
    for f in d.get("facts") or []:
        for k, v in f.items():
            sizes[k] += len(json.dumps(k)) + len(json.dumps(v, separators=(",", ":"))) + 2
    facts_chars = sum(sizes.values())
    sizes["(envelope + other top-level keys)"] = max(0, total - facts_chars)
    for k, v in sizes.items():
        acc["recall_fields"][k] += charged * v / total
    acc["recall_n_facts"].append(len(d.get("facts") or []))
    acc["recall_resp_chars"].append(total)


def new_acc() -> dict[str, Any]:
    return {"charged": defaultdict(float), "size": defaultdict(float), "output": defaultdict(float),
            "calls": defaultdict(int), "result_chars": defaultdict(int), "round_trip": defaultdict(float), "recall_fields": defaultdict(float),
            "recall_n_facts": [], "recall_resp_chars": [], "prefix_tokens_first_call": [], "api_calls": 0,
            "processes": 0, "negative_deltas": 0, "measured_total": 0, "result_total": 0}  # fmt: skip


def breakdown(run_dirs: list[Path]) -> dict[str, Any]:
    acc = new_acc()
    for rd in run_dirs:
        for f in sorted((rd / "transcripts").glob("*.jsonl")):
            attribute(parse_process(f), acc)
    total = acc["measured_total"] or 1
    rows: dict[str, dict[str, float]] = defaultdict(lambda: {"input_charged": 0.0, "output": 0.0})
    for k, v in acc["charged"].items():
        tool = k.split(" [")[0]
        rows[tool]["input_charged"] += v
    for k, v in acc["output"].items():
        rows[k]["output"] += v
    table = []
    for tool, r in rows.items():
        t = r["input_charged"] + r["output"]
        table.append({"component": tool, "tokens": round(t), "share": round(t / total, 4), "calls": acc["calls"].get(tool, 0),
                      "tokens_per_call": round(t / acc["calls"][tool]) if acc["calls"].get(tool) else None,
                      "request_tokens": round(acc["charged"].get(f"{tool} [request]", 0)),
                      "response_tokens": round(acc["charged"].get(f"{tool} [response]", 0)),
                      "output_tokens": round(r["output"]),
                      "response_size_tokens_avg": round(acc["size"].get(f"{tool} [response]", 0) / acc["calls"][tool])
                      if acc["calls"].get(tool) else None,
                      "response_chars_avg": round(acc["result_chars"].get(tool, 0) / acc["calls"][tool])
                      if acc["calls"].get(tool) else None})  # fmt: skip
    table.sort(key=lambda r: -r["tokens"])
    rt = sorted(({"component": k, "tokens": round(v), "share": round(v / total, 4), "calls": acc["calls"].get(k, 0),
                  "tokens_per_call": round(v / acc["calls"][k]) if acc["calls"].get(k) else None}
                 for k, v in acc["round_trip"].items()), key=lambda r: -r["tokens"])  # fmt: skip
    rf = acc["recall_fields"]
    rft = sum(rf.values()) or 1
    pf = acc["prefix_tokens_first_call"]
    return {
        "runs": [str(r) for r in run_dirs], "processes": acc["processes"], "api_calls": acc["api_calls"],
        "total_tokens_measured": acc["measured_total"], "total_tokens_result_events": acc["result_total"],
        "negative_deltas": acc["negative_deltas"],
        "prefix_tokens_first_call": {"min": min(pf) if pf else None, "max": max(pf) if pf else None,
                                     "mean": round(sum(pf) / len(pf)) if pf else None},
        "table": table,
        "round_trip": rt,
        "recall_response_by_field": sorted(({"field": k, "tokens": round(v), "share_of_recall_response": round(v / rft, 4)}
                                            for k, v in rf.items()), key=lambda r: -r["tokens"]),
        "recall_facts_per_response": {"n": len(acc["recall_n_facts"]),
                                      "mean": round(sum(acc["recall_n_facts"]) / max(1, len(acc["recall_n_facts"])), 1),
                                      "mean_chars": round(sum(acc["recall_resp_chars"]) / max(1, len(acc["recall_resp_chars"])))},
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", required=True, type=Path)
    ap.add_argument("--arms", default="P,B1,B0p")
    ap.add_argument("--seeds", default="")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    seeds = [s for s in a.seeds.split(",") if s] or sorted(p.name for p in a.runs.iterdir() if p.is_dir())
    out = {}
    for arm in a.arms.split(","):
        dirs = [a.runs / s / arm for s in seeds if (a.runs / s / arm / "transcripts").is_dir()]
        out[arm] = breakdown(dirs)
        b = out[arm]
        print(
            f"\n== {arm}: {len(dirs)} runs, {b['processes']} processes, {b['api_calls']} API calls, "
            f"{b['total_tokens_measured']:,} tokens (result events {b['total_tokens_result_events']:,}); "
            f"prefix/call {b['prefix_tokens_first_call']}"
        )
        for r in b["table"][:18]:
            print(f"  {r['component']:<44} {r['tokens']:>11,} {100*r['share']:5.1f}%  calls {r['calls']:>4}  "
                  f"per call {r['tokens_per_call'] or 0:>8,}  resp {r['response_tokens']:>10,}  req {r['request_tokens']:>8,} "
                  f"resp size/call {r['response_size_tokens_avg'] or 0:>6,}")  # fmt: skip
        print("  -- round-trip view (whole API call charged to the tool results that triggered it):")
        for r in b["round_trip"][:12]:
            print(f"  {r['component']:<44} {r['tokens']:>11,} {100*r['share']:5.1f}%  calls {r['calls']:>4}  "
                  f"per call {r['tokens_per_call'] or 0:>8,}")  # fmt: skip
        if b["recall_response_by_field"]:
            print("  recall response by field:", ", ".join(f"{r['field']} {100*r['share_of_recall_response']:.1f}%"
                                                      for r in b["recall_response_by_field"]))  # fmt: skip
            print("  recall facts/response:", b["recall_facts_per_response"])
    if a.out:
        a.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
