"""Trials 3/4 runner (option-2 design): 4 fresh, independent `claude -p` sessions per run against
a private copy of the tinytasks repo. Nothing carries over between sessions except the repo
(files + git history) and whichever memory the arm provides.

Arms (same model, same task prompts; only the memory line differs):
  baseline  - plain Claude Code, no memory instruction (decisions survive only if the agent
              happens to write them into code, commit messages or a file on its own)
  claudemd  - Claude Code's native memory: told to keep lasting decisions in CLAUDE.md, which
              Claude Code auto-loads in every later session
  plexus    - told to keep lasting decisions in Plexus (MCP), and to recall before changing code;
              fresh, empty tenant per run

Usage:
  python run_trial_3_4_v2.py --arm plexus --run-id r1
  python run_trial_3_4_v2.py --arm baseline --run-id r1 --sessions 1      # smoke: session 1 only
Outputs: ../logs/t34/<arm>_<run-id>/{repo, snap_s1..s4, session_N.jsonl, summary.json}
"""
import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC_REPO = HERE.parent / "repo" / "tinytasks"
PROMPTS = json.loads((HERE.parent / "repo" / "session_prompts_v2.json").read_text(encoding="utf-8"))
LOGS = HERE.parent / "logs" / "t34"
PLEXUS_URL = "http://127.0.0.1:8766/mcp/t/{tenant}"
MODEL = "sonnet"

NOTES = {
    "baseline": {"first": "", "later": ""},
    "claudemd": {
        "first": "\n\nTeam convention: lasting decisions and conventions for this repo are recorded in "
                 "CLAUDE.md at the repo root (Claude Code loads it automatically in future sessions).",
        "later": "",
    },
    "plexus": {
        "first": "\n\nTeam convention: lasting decisions and conventions for this repo are recorded in the "
                 "team's Plexus memory (MCP server 'plexus'). Call start_session, then record each "
                 "decision with assert_fact.",
        "later": "\n\nTeam convention: this repo's lasting decisions and conventions are kept in the team's "
                 "Plexus memory (MCP server 'plexus'). Call start_session, then recall what's relevant "
                 "before you change code.",
    },
}
SESSIONS = [("session_1", "session_1_change"), ("session_2", "session_2"),
            ("session_3", "session_3"), ("session_4", "session_4")]


def force_rmtree(path: Path) -> None:
    def on_err(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.exists():
        shutil.rmtree(path, onerror=on_err)


def run_session(repo: Path, prompt: str, mcp: dict, log_path: Path) -> dict:
    cmd = ["claude", "-p", prompt, "--model", MODEL,
           "--output-format", "stream-json", "--verbose",
           "--dangerously-skip-permissions",
           "--tools", "Read,Write,Edit,Bash,Grep,Glob",
           "--strict-mcp-config", "--mcp-config", json.dumps(mcp),
           "--setting-sources", "project",
           "--session-id", str(uuid.uuid4())]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env["TINYTASKS_DATA"] = str(repo.parent / "scratch_data.json")  # keep stray CLI runs out of the repo
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, cwd=repo, stdout=fh, stderr=subprocess.PIPE, text=True,
                              env=env, timeout=1200)
    result = {"returncode": proc.returncode, "seconds": round(time.time() - t0, 1)}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "result":
            result.update(cost_usd=msg.get("total_cost_usd") or 0.0, num_turns=msg.get("num_turns"),
                          is_error=msg.get("is_error"), result=(msg.get("result") or "")[:1500],
                          usage=msg.get("usage"))
    if proc.returncode != 0:
        result["stderr"] = proc.stderr[-1500:]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=list(NOTES), required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--sessions", type=int, default=4)
    ap.add_argument("--max-cost", type=float, default=4.0)
    ap.add_argument("--handoff", choices=["none", "clone"], default="none",
                    help="clone: after session 1, `git clone` the repo to a new path and run sessions 2-4 "
                         "there - only committed files travel (a teammate / fresh checkout picking it up)")
    a = ap.parse_args()

    run_dir = LOGS / f"{a.arm}_{a.run_id}"
    force_rmtree(run_dir)
    run_dir.mkdir(parents=True)
    repo = run_dir / "repo"
    shutil.copytree(SRC_REPO, repo, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "data.json"))

    tenant = f"t34_{a.arm}_{a.run_id}_{uuid.uuid4().hex[:6]}"
    mcp = ({"mcpServers": {"plexus": {"type": "http", "url": PLEXUS_URL.format(tenant=tenant)}}}
           if a.arm == "plexus" else {"mcpServers": {}})

    summary = {"arm": a.arm, "run_id": a.run_id, "model": MODEL, "tenant": tenant if a.arm == "plexus" else None,
               "handoff": a.handoff, "sessions": {}, "total_cost_usd": 0.0}
    work = repo
    for i, (label, key) in enumerate(SESSIONS[: a.sessions], start=1):
        if i == 2 and a.handoff == "clone":
            work = run_dir / "repo_b"
            subprocess.run(["git", "clone", "-q", str(repo), str(work)], check=True)
        note = NOTES[a.arm]["first" if i == 1 else "later"]
        res = run_session(work, PROMPTS[key] + note, mcp, run_dir / f"{label}.jsonl")
        res["cwd"] = str(work)
        summary["sessions"][label] = res
        summary["total_cost_usd"] = round(summary["total_cost_usd"] + res.get("cost_usd", 0.0), 4)
        shutil.copytree(work, run_dir / f"snap_s{i}",
                        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        print(f"[{a.arm} {a.run_id}] {label}: rc={res['returncode']} {res['seconds']}s "
              f"${res.get('cost_usd', 0):.3f} (total ${summary['total_cost_usd']:.2f})", flush=True)
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if summary["total_cost_usd"] > a.max_cost:
            print(f"STOPPED: over --max-cost ${a.max_cost}", flush=True)
            break


if __name__ == "__main__":
    main()
