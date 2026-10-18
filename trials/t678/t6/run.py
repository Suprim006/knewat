"""Trial 6 runner: a decision that spans two repos.

Per run: a run dir with two SEPARATE git repos side by side,
    <run_dir>/tinytasks   (A: the task tracker; session 1 runs here)
    <run_dir>/tasksync    (B: exporter CLI that reads A's JSON data file; sessions 2-4 run here)
Four fresh, independent `claude -p` processes (never --resume). Nothing carries over between
sessions except the files on disk (both repos + git history) and whichever memory the arm provides.

Arms (same model, same task prompts; only the memory sentence differs):
  baseline  - no memory instruction
  claudemd  - told that the team's lasting decisions are kept in CLAUDE.md (no location given)
  plexus    - told that they are kept in the team's Plexus memory (MCP); fresh tenant per run

Usage:
  python3 run.py --arm plexus --run-id r1
  python3 run.py --arm baseline --run-id smoke1 --sessions 4 --max-cost 1.5     # smoke
Outputs: ../../logs/t6/<arm>_<run-id>/{tinytasks, tasksync, snap_s1..s4/{tinytasks,tasksync},
         session_N.jsonl, summary.json, prompts_used.json}
"""
import argparse
import json
import os
import shutil
import stat
import subprocess
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
PROMPTS = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
LOGS = HERE.parent.parent / "logs" / "t6"
MODEL = "sonnet"
SESSIONS = [("session_1", "tinytasks"), ("session_2", "tasksync"),
            ("session_3", "tasksync"), ("session_4", "tasksync")]
GIT_ID = ["-c", "user.name=trial", "-c", "user.email=trial@example.invalid"]
IGNORE = shutil.ignore_patterns("__pycache__", ".pytest_cache")
GIT_BASH_CANDIDATES = ["C:/Change_folder_after_HDD/Git/bin/bash.exe", "C:/Program Files/Git/bin/bash.exe"]


def git_bash_path() -> str | None:
    """Claude Code on Windows only offers the Bash tool when it can find git-bash; from an MSYS shell it
    does not find it by itself (smoke1 ran with NO Bash tool), so pass it explicitly."""
    env = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if env and Path(env).exists():
        return env
    return next((c for c in GIT_BASH_CANDIDATES if Path(c).exists()), None)


def force_rmtree(path: Path) -> None:
    def on_err(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.exists():
        shutil.rmtree(path, onerror=on_err)


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *GIT_ID, *args], cwd=repo, capture_output=True, text=True)
    return r.stdout.strip()


def make_repo(name: str, dest: Path) -> None:
    shutil.copytree(FIXTURES / name, dest, ignore=IGNORE)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=dest, check=True)
    git(dest, "add", "-A")
    git(dest, "commit", "-q", "-m", "initial commit")  # neutral message only


def find_claude_md(run_dir: Path) -> dict:
    """Every CLAUDE.md under the run dir (both repos + the shared parent), and whether committed."""
    found = {}
    cands = [run_dir / "CLAUDE.md"]
    for d in ("tinytasks", "tasksync"):
        cands += list((run_dir / d).rglob("CLAUDE.md"))
    for p in cands:
        if not p.exists():
            continue
        repo = p.parent
        while repo != run_dir and not (repo / ".git").exists():
            repo = repo.parent
        tracked = False
        if (repo / ".git").exists():
            tracked = bool(git(repo, "ls-files", str(p.relative_to(repo)).replace("\\", "/")))
        found[str(p.relative_to(run_dir)).replace("\\", "/")] = {"committed": tracked, "bytes": p.stat().st_size}
    return found


def repo_state(repo: Path) -> dict:
    return {"head": git(repo, "rev-parse", "--short", "HEAD"),
            "commits": int(git(repo, "rev-list", "--count", "HEAD") or 0),
            "dirty": bool(git(repo, "status", "--porcelain"))}


def run_session(cwd: Path, prompt: str, mcp: dict, log_path: Path, extra_env: dict) -> dict:
    cmd = ["claude", "-p"]
    stdin = None
    if len(prompt) < 7000:
        cmd.append(prompt)
    else:
        stdin = prompt
    cmd += ["--model", MODEL, "--output-format", "stream-json", "--verbose",
            "--dangerously-skip-permissions",
            "--tools", "Read,Write,Edit,Bash,Grep,Glob",
            "--strict-mcp-config", "--mcp-config", json.dumps(mcp),
            "--setting-sources", "project",
            "--session-id", str(uuid.uuid4())]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("TINYTASKS_DATA", None)
    env.update(extra_env)
    gb = git_bash_path()
    if gb:
        env["CLAUDE_CODE_GIT_BASH_PATH"] = gb
    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, cwd=cwd, input=stdin, stdout=fh, stderr=subprocess.PIPE, text=True,
                              env=env, timeout=1200)
    result = {"returncode": proc.returncode, "seconds": round(time.time() - t0, 1)}
    tool_counts: dict[str, int] = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = msg.get("type")
        if t == "system" and msg.get("subtype") == "init":
            result["mcp_servers"] = msg.get("mcp_servers")
            result["n_tools_listed"] = len(msg.get("tools") or [])
            result["builtin_tools_listed"] = sorted(x for x in (msg.get("tools") or []) if not x.startswith("mcp__"))
            result["plexus_tools_listed"] = sorted(x for x in (msg.get("tools") or []) if x.startswith("mcp__plexus__"))
        elif t == "assistant":
            for b in (msg.get("message") or {}).get("content") or []:
                if b.get("type") == "tool_use":
                    tool_counts[b.get("name", "?")] = tool_counts.get(b.get("name", "?"), 0) + 1
        elif t == "result":
            result.update(cost_usd=msg.get("total_cost_usd") or 0.0, num_turns=msg.get("num_turns"),
                          is_error=msg.get("is_error"), permission_denials=msg.get("permission_denials"),
                          result=(msg.get("result") or "")[:4000], usage=msg.get("usage"))
    result["tool_counts"] = tool_counts
    if proc.returncode != 0:
        result["stderr"] = proc.stderr[-1500:]
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["baseline", "claudemd", "plexus"], required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--sessions", type=int, default=4)
    ap.add_argument("--max-cost", type=float, default=3.0)
    ap.add_argument("--plexus-url", default="http://127.0.0.1:8766")
    a = ap.parse_args()

    run_dir = LOGS / f"{a.arm}_{a.run_id}"
    force_rmtree(run_dir)
    run_dir.mkdir(parents=True)
    repos = {"tinytasks": run_dir / "tinytasks", "tasksync": run_dir / "tasksync"}
    for name, dest in repos.items():
        make_repo(name, dest)

    tenant = f"t6_{a.arm}_{a.run_id}_{uuid.uuid4().hex[:6]}".lower()
    assert len(tenant) <= 48, tenant
    mcp = ({"mcpServers": {"plexus": {"type": "http", "url": f"{a.plexus_url.rstrip('/')}/mcp/t/{tenant}"}}}
           if a.arm == "plexus" else {"mcpServers": {}})

    summary = {"arm": a.arm, "run_id": a.run_id, "model": MODEL, "tenant": tenant if a.arm == "plexus" else None,
               "run_dir": str(run_dir), "initial_state": {n: repo_state(p) for n, p in repos.items()},
               "sessions": {}, "total_cost_usd": 0.0}
    used = {}
    for i, (label, repo_name) in enumerate(SESSIONS[: a.sessions], start=1):
        sentence = PROMPTS["arm_sentences"][a.arm]["first" if i == 1 else "later"]
        prompt = PROMPTS[label] + sentence
        used[label] = prompt
        cwd = repos[repo_name]
        # keep stray CLI runs of tinytasks from writing a data file into either repo
        extra = {"TINYTASKS_DATA": str(run_dir / "scratch_data.json")} if i == 1 else {}
        res = run_session(cwd, prompt, mcp, run_dir / f"{label}.jsonl", extra)
        res["cwd"] = str(cwd)
        res["claude_md_files_after"] = find_claude_md(run_dir)
        res["repo_state_after"] = {n: repo_state(p) for n, p in repos.items()}
        summary["sessions"][label] = res
        summary["total_cost_usd"] = round(summary["total_cost_usd"] + (res.get("cost_usd") or 0.0), 4)
        snap = run_dir / f"snap_s{i}"
        for n, p in repos.items():
            shutil.copytree(p, snap / n, ignore=IGNORE)
        if "Bash" not in (res.get("builtin_tools_listed") or []):
            print(f"ABORT: the Bash tool was not offered to {label} (tools: {res.get('builtin_tools_listed')}); "
                  f"set CLAUDE_CODE_GIT_BASH_PATH. Run is invalid.", flush=True)
            (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            raise SystemExit(3)
        print(f"[{a.arm} {a.run_id}] {label} (cwd {repo_name}): rc={res['returncode']} {res['seconds']}s "
              f"${res.get('cost_usd') or 0:.3f} turns={res.get('num_turns')} denials={len(res.get('permission_denials') or [])} "
              f"(total ${summary['total_cost_usd']:.2f})", flush=True)
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (run_dir / "prompts_used.json").write_text(json.dumps(used, indent=2), encoding="utf-8")
        if summary["total_cost_usd"] > a.max_cost:
            print(f"STOPPED: over --max-cost ${a.max_cost}", flush=True)
            break


if __name__ == "__main__":
    main()
