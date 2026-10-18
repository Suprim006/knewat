"""Trial 8 runner: provenance + contradiction tracking. 3 fresh `claude -p` sessions per run on one repo.

  session 1 (builder-1): two pasted documents (compliance memo draft v0.3: C1-C3; product spec v2: P1, P2==C1)
                         -> implement all rules in different commands; claudemd/plexus record rule + source doc
  session 2 (builder-2): teammate request that silently contradicts C2 (keep emails as typed)
  session 3 (builder-3): "the memo is void: remove what came only from it, keep what another source requires,
                         list removed/kept"

The documents live ONLY in prompts.json (outside every workdir) and in the session streams under logs/. The live
workdir sits outside logs/ (WORK_ROOT), so `..` from the repo reaches neither prompts nor streams. The harness
commits only the neutral fixture; it never commits or writes the documents anywhere an agent can read.

Usage:
  python3 run.py --arm plexus --run-id r1 [--plexus-url http://127.0.0.1:8766] [--max-cost 3] [--sessions 3]
Outputs: ../../logs/t8/<arm>_<run-id>/{session_N.jsonl, snap_sN/, summary.json}
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
FIXTURE = HERE / "fixtures" / "tinytasks"
P = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
TRIALS = HERE.parent.parent
LOGS = TRIALS / "logs" / "t8"
WORK_ROOT = TRIALS / "work_t8"          # live workdirs: NOT under logs/, so ../ holds no streams or prompts
MODEL = "sonnet"
SESSIONS = ["session_1", "session_2", "session_3"]
GIT_ENV = {"GIT_AUTHOR_NAME": "tinytasks-dev", "GIT_AUTHOR_EMAIL": "dev@tinytasks.example",
           "GIT_COMMITTER_NAME": "tinytasks-dev", "GIT_COMMITTER_EMAIL": "dev@tinytasks.example"}


def git_bash_path() -> str | None:
    """Claude Code on Windows only offers the Bash tool if it can find git-bash; set it explicitly."""
    env = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    cands = [env] if env else []
    cands += ["C:/Change_folder_after_HDD/Git/bin/bash.exe", "C:/Program Files/Git/bin/bash.exe"]
    git = shutil.which("git")
    if git:
        cands.append(str(Path(git).resolve().parent.parent / "bin" / "bash.exe"))
    for c in cands:
        if c and Path(c).exists():
            return str(Path(c))
    return None


def force_rmtree(path: Path) -> None:
    def on_err(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.exists():
        shutil.rmtree(path, onerror=on_err)


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    return (r.stdout or "").strip()


def build_repo(repo: Path) -> None:
    """Fixture + neutral commit. No rule, document or decision is written anywhere."""
    shutil.copytree(FIXTURE, repo, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "data.json"))
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial commit")


def run_session(repo: Path, prompt: str, mcp: dict, log_path: Path, session_id: str, scratch: Path) -> dict:
    cmd = ["claude", "-p"]
    stdin_data = None
    if len(prompt) < 8000:
        cmd.append(prompt)
    else:
        stdin_data = prompt
    cmd += ["--model", MODEL, "--output-format", "stream-json", "--verbose",
            "--dangerously-skip-permissions",
            "--tools", "Read,Write,Edit,Bash,Grep,Glob",
            "--strict-mcp-config", "--mcp-config", json.dumps(mcp),
            "--setting-sources", "project",
            "--session-id", session_id]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    gb = git_bash_path()
    if gb:
        env["CLAUDE_CODE_GIT_BASH_PATH"] = gb
    env["TINYTASKS_DATA"] = str(scratch)          # keep stray CLI runs out of the repo
    t0 = time.time()
    res = {}
    with open(log_path, "w", encoding="utf-8") as fh:
        try:
            proc = subprocess.run(cmd, cwd=repo, input=stdin_data, stdout=fh, stderr=subprocess.PIPE, text=True,
                                  env=env, timeout=1200)
            res["returncode"] = proc.returncode
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            res["returncode"] = -9
            stderr = "TIMEOUT 1200s"
    res["seconds"] = round(time.time() - t0, 1)
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "system" and msg.get("subtype") == "init":
            res["mcp_servers"] = msg.get("mcp_servers")
            res["tools"] = [t for t in msg.get("tools", []) if not t.startswith("mcp__")]
            res["n_plexus_tools"] = len([t for t in msg.get("tools", []) if t.startswith("mcp__plexus__")])
        if msg.get("type") == "result":
            res.update(cost_usd=msg.get("total_cost_usd") or 0.0, num_turns=msg.get("num_turns"),
                       is_error=msg.get("is_error"), result=msg.get("result") or "",
                       permission_denials=msg.get("permission_denials") or [], usage=msg.get("usage"))
    if res.get("returncode") != 0:
        res["stderr"] = (stderr or "")[-1500:]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["baseline", "claudemd", "plexus"], required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--plexus-url", default="http://127.0.0.1:8766")
    ap.add_argument("--max-cost", type=float, default=3.0)
    ap.add_argument("--sessions", type=int, default=3)
    a = ap.parse_args()

    name = f"{a.arm}_{a.run_id}"
    run_dir = LOGS / name
    force_rmtree(run_dir)
    run_dir.mkdir(parents=True)
    work_parent = WORK_ROOT / name
    force_rmtree(work_parent)
    work_parent.mkdir(parents=True)
    repo = work_parent / "repo"
    build_repo(repo)
    base_sha = git(repo, "rev-parse", "HEAD")
    shutil.copytree(repo, run_dir / "snap_s0")

    tenant = f"t8_{a.arm}_{a.run_id}_{uuid.uuid4().hex[:6]}"
    mcp = ({"mcpServers": {"plexus": {"type": "http", "url": f"{a.plexus_url}/mcp/t/{tenant}"}}}
           if a.arm == "plexus" else {"mcpServers": {}})
    summary = {"trial": 8, "arm": a.arm, "run_id": a.run_id, "model": MODEL,
               "tenant": tenant if a.arm == "plexus" else None, "workdir": str(repo), "base_sha": base_sha,
               "agent_ids": P["agent_ids"], "sessions": {}, "total_cost_usd": 0.0}
    for i, label in enumerate(SESSIONS[: a.sessions], start=1):
        note = P["notes"][a.arm]["first" if i == 1 else "later"]
        sid = str(uuid.uuid4())
        res = run_session(repo, P["sessions"][label] + note, mcp, run_dir / f"{label}.jsonl", sid,
                          work_parent / "scratch_data.json")
        res.update(cwd=str(repo), claude_session_id=sid, head_after=git(repo, "rev-parse", "HEAD"),
                   dirty_after=bool(git(repo, "status", "--porcelain")))
        summary["sessions"][label] = res
        summary["total_cost_usd"] = round(summary["total_cost_usd"] + (res.get("cost_usd") or 0.0), 4)
        shutil.copytree(repo, run_dir / f"snap_s{i}", ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        print(f"[{a.arm} {a.run_id}] {label}: rc={res['returncode']} {res['seconds']}s ${res.get('cost_usd', 0):.3f} "
              f"turns={res.get('num_turns')} denials={len(res.get('permission_denials') or [])} "
              f"(total ${summary['total_cost_usd']:.2f})", flush=True)
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        if "Bash" not in (res.get("tools") or []):
            print("ABORT: Bash tool not offered (git-bash not found?)", flush=True)
            break
        if a.arm == "plexus" and i == 1 and not res.get("n_plexus_tools"):
            print("ABORT: plexus tools not listed in session 1 (server down?)", flush=True)
            break
        if summary["total_cost_usd"] > a.max_cost:
            print(f"STOPPED: over --max-cost ${a.max_cost}", flush=True)
            break


if __name__ == "__main__":
    main()
