"""Trials 1/2 runner (v2): ONE continuous claude -p session (--session-id, then --resume),
100 prompts, Haiku. Long-form sections push the conversation past the context window, so
Claude Code's own auto-compaction kicks in - which is the point.

Arms:
  baseline  - plain Claude Code, no tools at all; the only memory is the conversation itself
  plexus    - same, plus the Plexus MCP server (fresh empty tenant) and a standing system note
              to record the rules with assert_fact and recall them before writing

Usage:
  python run_trial_1_2_v2.py --arm baseline --run-id r1
  python run_trial_1_2_v2.py --arm plexus --run-id r1 --limit 5      # smoke test
Outputs ../logs/t12/<arm>_<run-id>/{turns.jsonl, transcript.json}. Resumable: re-running with the
same run-id continues from the last completed turn.
"""
import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE.parent / "logs" / "t12"
PLEXUS_URL = "http://127.0.0.1:8766/mcp/t/{tenant}"
MODEL = "haiku"

PLEXUS_NOTE = (
    "You have the team's Plexus memory available (MCP server 'plexus': start_session, assert_fact, "
    "recall, ...). This is a very long session and early messages will scroll out of your context. "
    "Call start_session once. Record every standing rule or convention the user sets with assert_fact "
    "as soon as it's set, and call recall to check the standing rules before writing each section."
)


def call(prompt: str, state: dict, arm: str, first: bool, turn_log: Path) -> dict:
    cmd = ["claude", "-p", prompt, "--model", MODEL,
           "--output-format", "stream-json", "--verbose",
           "--dangerously-skip-permissions", "--tools", "",
           "--strict-mcp-config", "--mcp-config", json.dumps(state["mcp"]),
           "--setting-sources", "project"]
    cmd += ["--session-id", state["session_id"]] if first else ["--resume", state["session_id"]]
    if arm == "plexus":
        cmd += ["--append-system-prompt", PLEXUS_NOTE]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=state["cwd"], capture_output=True, text=True, env=env, timeout=900)
    out = {"returncode": proc.returncode, "seconds": round(time.time() - t0, 1), "tool_calls": [],
           "api_calls": []}
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "assistant":
            m = msg.get("message") or {}
            u = m.get("usage") or {}
            out["api_calls"].append(u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                                    + u.get("cache_creation_input_tokens", 0))
            for b in m.get("content") or []:
                if b.get("type") == "tool_use":
                    out["tool_calls"].append(b.get("name", ""))
        elif msg.get("type") == "system" and msg.get("subtype") == "compact_boundary":
            out["compacted"] = True
        elif msg.get("type") == "result":
            out.update(text=msg.get("result") or "", cost_usd=msg.get("total_cost_usd") or 0.0,
                       is_error=msg.get("is_error"), usage=msg.get("usage"))
    out["context_tokens_last_call"] = out["api_calls"][-1] if out["api_calls"] else None
    if proc.returncode != 0:
        out["stderr"] = proc.stderr[-1500:]
    with open(turn_log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(out) + "\n")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["baseline", "plexus"], required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--max-cost", type=float, default=12.0)
    ap.add_argument("--prompts", default=str(HERE / "trial1_2_prompts_v2.json"))
    a = ap.parse_args()

    skip = LOGS / f"SKIP_{a.arm}_{a.run_id}"
    if skip.exists():
        print(f"[{a.arm} {a.run_id}] held by {skip.name} (delete it and re-run to release)", flush=True)
        return

    prompts = json.loads(Path(a.prompts).read_text(encoding="utf-8"))["prompts"]
    run_dir = LOGS / f"{a.arm}_{a.run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path, turn_log = run_dir / "state.json", run_dir / "turns.jsonl"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not state.get("cost_fixed_v2") and turn_log.exists():
            # migrate a v1 state (sum of running totals) to the true session total
            seen = [json.loads(l).get("cost_usd") or 0.0
                    for l in turn_log.read_text(encoding="utf-8").splitlines() if l.strip()]
            state["cost_sum_of_running_totals_v1"] = state["cost"]
            state["cost"] = round(max(seen, default=0.0), 4)
        state["cost_fixed_v2"] = True
    else:
        tenant = f"t12_{a.arm}_{a.run_id}_{uuid.uuid4().hex[:6]}"
        cwd = run_dir / "cwd"
        cwd.mkdir(exist_ok=True)
        state = {"session_id": str(uuid.uuid4()), "cwd": str(cwd), "done": 0, "cost": 0.0,
                 "tenant": tenant if a.arm == "plexus" else None,
                 "mcp": ({"mcpServers": {"plexus": {"type": "http", "url": PLEXUS_URL.format(tenant=tenant)}}}
                         if a.arm == "plexus" else {"mcpServers": {}})}

    while state["done"] < min(a.limit, len(prompts)):
        i = state["done"]
        res = call(prompts[i], state, a.arm, first=(i == 0), turn_log=turn_log)
        if res["returncode"] != 0 or res.get("is_error") or not res.get("text"):
            print(f"[{a.arm} {a.run_id}] turn {i + 1} failed, retrying once: {res.get('stderr', '')[:300]}",
                  flush=True)
            time.sleep(20)
            res = call(prompts[i], state, a.arm, first=(i == 0), turn_log=turn_log)
            if res["returncode"] != 0 or not res.get("text"):
                print(f"[{a.arm} {a.run_id}] turn {i + 1} failed twice; stopping (resumable).", flush=True)
                break
        state["done"] += 1
        # total_cost_usd from `claude -p --resume` is the SESSION's running total, not this turn's
        # cost (verified 2026-10-17: it rises monotonically, and the turn-to-turn step matches one
        # context re-read). v1 summed these running totals, which inflated cost (A6).
        state["cost"] = round(max(state["cost"], res.get("cost_usd", 0.0)), 4)
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        print(f"[{a.arm} {a.run_id}] {i + 1}/100 ctx={res.get('context_tokens_last_call')} "
              f"tools={len(res['tool_calls'])} {'COMPACTED ' if res.get('compacted') else ''}"
              f"${res.get('cost_usd', 0):.3f} total=${state['cost']:.2f}", flush=True)
        if state["cost"] > a.max_cost:
            print(f"STOPPED: over --max-cost ${a.max_cost}", flush=True)
            break

    # assemble transcript for the scorer from the last successful attempt of each turn
    turns = [json.loads(l) for l in turn_log.read_text(encoding="utf-8").splitlines() if l.strip()]
    ok = [t for t in turns if t["returncode"] == 0 and t.get("text")]
    (run_dir / "transcript.json").write_text(json.dumps({
        "arm": a.arm, "run_id": a.run_id, "model": MODEL, "n_completed": len(ok[: state["done"]]),
        "total_cost_usd": state["cost"],
        "responses": [t["text"] for t in ok[: state["done"]]],
        "context_tokens": [t.get("context_tokens_last_call") for t in ok[: state["done"]]],
        "compacted_at": [n + 1 for n, t in enumerate(ok[: state["done"]]) if t.get("compacted")],
        "tool_calls": [t["tool_calls"] for t in ok[: state["done"]]],
    }, indent=2), encoding="utf-8")
    print(f"done: {state['done']} turns, ${state['cost']:.2f}", flush=True)


if __name__ == "__main__":
    main()
