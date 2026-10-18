"""Trial 7 runner: memory shared between different agents on parallel git worktrees + a non-LLM ci-bot.

Per run (fresh dir, fresh Plexus tenant):
  main checkout  <run>/tinytasks   (fixture committed on `main` with a neutral message, nothing else)
  worktrees      <run>/wt_a (branch feat-a), <run>/wt_b (branch feat-b), both from the same main commit
  1. session A  : agent 'planner-builder', sonnet, cwd wt_a  - feature + team decision Y1, commits on feat-a
  2. session B1 : agent 'builder-2',       haiku,  cwd wt_b  - two features that each touch Y1
  3. ci-bot     : plain Python, no LLM. plexus arm: assert_fact (source kind 'tool') over MCP HTTP as
                  agent 'ci-bot'. baseline/claudemd: appends the same text to <run>/tinytasks/CI_NOTES.md
                  (main checkout, uncommitted; nothing auto-loads it)
  4. session B2 : agent 'builder-2',       haiku,  cwd wt_b  - one feature where calling the deprecated
                  get_overdue_tasks is the natural shortcut (Y2)
The harness never merges feat-a. Each session is a fresh `claude -p` process (no --resume).

Usage: python3 run.py --arm {baseline,claudemd,plexus} --run-id r1 [--max-cost 3] [--stop-after A|B1|B2]
Outputs: ../../logs/t7/<arm>_<run-id>/{tinytasks,wt_a,wt_b,snap_*,session_*.jsonl,git_state_*.json,summary.json,...}
"""
import argparse
import datetime
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from plexus_mcp import Plexus  # noqa: E402

FIXTURE = HERE / "fixtures" / "tinytasks"
PROMPTS = json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))
LOGS = HERE.parent.parent / "logs" / "t7"
PROJECTS = Path.home() / ".claude" / "projects"
SESSIONS = [("A", "session_A", "wt_a"), ("B1", "session_B1", "wt_b"), ("B2", "session_B2", "wt_b")]
SNAP_IGNORE = shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache")


def force_rmtree(path: Path) -> None:
    def on_err(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    if path.exists():
        shutil.rmtree(path, onerror=on_err)


def git(cwd: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {r.stderr}")
    return r.stdout.strip()


def mangle(path: Path) -> str:
    """Claude Code's per-project dir name: absolute path with each of : \\ / _ . replaced by -."""
    return re.sub(r"[:\\/_.]", "-", str(path.resolve()))


def projects_listing(run_dir: Path) -> dict:
    """Every ~/.claude/projects dir that belongs to this run's paths -> its memory/*.md files."""
    prefix = mangle(run_dir)
    out = {}
    if PROJECTS.exists():
        for d in sorted(PROJECTS.iterdir()):
            if d.name.startswith(prefix):
                mem = d / "memory"
                out[d.name] = sorted(p.name for p in mem.glob("*")) if mem.exists() else []
    return out


def setup_repos(run_dir: Path) -> dict:
    main = run_dir / "tinytasks"
    shutil.copytree(FIXTURE, main, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "data.json"))
    git(main, "init", "-q", "-b", "main")
    git(main, "config", "user.name", "Trial Harness")
    git(main, "config", "user.email", "harness@example.invalid")
    git(main, "add", "-A")
    git(main, "commit", "-q", "-m", "initial import")
    git(main, "worktree", "add", "-q", "-b", "feat-a", str(run_dir / "wt_a"), "main")
    git(main, "worktree", "add", "-q", "-b", "feat-b", str(run_dir / "wt_b"), "main")
    return {"main": main, "wt_a": run_dir / "wt_a", "wt_b": run_dir / "wt_b"}


def git_state(paths: dict) -> dict:
    main = paths["main"]
    st = {"worktree_list": git(main, "worktree", "list", "--porcelain", check=False),
          "branches": {}, "status": {}, "claude_md_tracked": {}}
    for br in ("main", "feat-a", "feat-b"):
        st["branches"][br] = {
            "sha": git(main, "rev-parse", br, check=False),
            "log": git(main, "log", "--format=%h %s", br, check=False).splitlines(),
            "files": git(main, "ls-tree", "-r", "--name-only", br, check=False).splitlines(),
        }
        st["claude_md_tracked"][br] = [f for f in st["branches"][br]["files"] if f.lower().endswith("claude.md")]
    for name, p in paths.items():
        st["status"][name] = git(p, "status", "--porcelain", check=False).splitlines()
    return st


def has_result(log_path: Path) -> bool:
    """True once the stream contains the final `result` message."""
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 30000))
            return b'"type":"result"' in f.read()
    except OSError:
        return False


def end_process_tree(pid: int) -> None:
    """Stop a `claude -p` process THIS RUNNER started (and its children) on Windows."""
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def run_session(cwd: Path, prompt: str, model: str, mcp: dict, log_path: Path, scratch: Path) -> dict:
    cmd = ["claude", "-p", prompt, "--model", model,
           "--output-format", "stream-json", "--verbose",
           "--dangerously-skip-permissions",
           "--tools", "Read,Write,Edit,Bash,Grep,Glob",
           "--strict-mcp-config", "--mcp-config", json.dumps(mcp),
           "--setting-sources", "project",
           "--session-id", str(uuid.uuid4())]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env["TINYTASKS_DATA"] = str(scratch)  # keep stray CLI runs out of the repos
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    t0 = time.time()
    timed_out = killed_after_result = False
    err_path = log_path.with_suffix(".stderr")
    with open(log_path, "w", encoding="utf-8") as fh, open(err_path, "w", encoding="utf-8") as eh:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=fh, stderr=eh, text=True, env=env)
        result_seen_at = None
        while True:
            try:
                rc = proc.wait(timeout=3)
                break
            except subprocess.TimeoutExpired:
                pass
            now = time.time()
            if result_seen_at is None and has_result(log_path):
                result_seen_at = now
            # claude can linger after its final result when the agent left a background task running
            # (seen in smoke: a `find /` over the whole disk). Grace period, then end the process tree.
            if result_seen_at is not None and now - result_seen_at > 30:
                end_process_tree(proc.pid)
                killed_after_result = True
                rc = proc.wait()
                break
            if now - t0 > 1200:
                end_process_tree(proc.pid)
                timed_out = True
                rc = proc.wait()
                break
    stderr = err_path.read_text(encoding="utf-8", errors="replace")
    res = {"returncode": rc, "seconds": round(time.time() - t0, 1), "timed_out": timed_out,
           "killed_after_result": killed_after_result, "cwd": str(cwd), "model_requested": model}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "system" and msg.get("subtype") == "init":
            res.update(model=msg.get("model"), session_id=msg.get("session_id"),
                       memory_paths=msg.get("memory_paths"), init_cwd=msg.get("cwd"),
                       mcp_servers=msg.get("mcp_servers"))
        if msg.get("type") == "result":
            denials = msg.get("permission_denials") or []
            res.update(cost_usd=msg.get("total_cost_usd") or 0.0, num_turns=msg.get("num_turns"),
                       is_error=msg.get("is_error"), result=(msg.get("result") or "")[:1500],
                       permission_denials=len(denials),
                       permission_denial_tools=sorted({d.get("tool_name", "?") for d in denials if isinstance(d, dict)}),
                       usage=msg.get("usage"))
    if rc != 0:
        res["stderr"] = stderr[-1500:]
    return res


def ci_bot(arm: str, paths: dict, tenant: str, plexus_url: str) -> dict:
    """Plain Python, no LLM. Records Y2 where a native team (baseline/claudemd) or Plexus would."""
    cfg = PROMPTS["ci_bot"]
    if arm == "plexus":
        p = Plexus(tenant, plexus_url, cfg["agent_id"])
        src = p.call("add_source", title=cfg["source_title"], kind="tool", text=cfg["value"])
        sid = src.get("source_id")
        fact = p.call("assert_fact", subject=cfg["subject"], predicate=cfg["predicate"], value=cfg["value"],
                      scope="global", source_id=sid) if sid else {"error": "no source_id", "source": src}
        return {"where": "plexus", "agent_id": cfg["agent_id"], "source": src, "fact": fact}
    notes = paths["main"] / "CI_NOTES.md"
    new = not notes.exists()
    with open(notes, "a", encoding="utf-8", newline="\n") as fh:
        if new:
            fh.write("# CI notes\n\nAutomated notes from the CI pipeline.\n\n")
        fh.write(f"- {datetime.date.today().isoformat()} (ci-bot): {cfg['notes_line']}\n")
    return {"where": "CI_NOTES.md (main checkout, uncommitted)", "path": str(notes), "created": new,
            "tracked": bool(git(paths["main"], "ls-files", "CI_NOTES.md", check=False))}


def plexus_dump(tenant: str, plexus_url: str) -> dict:
    out = {}
    try:
        p = Plexus(tenant, plexus_url, "harness-audit")
        for q in ("due date rounding whole minute", "deprecated function do not call", "team decision convention"):
            r = p.call("recall", query=q, k=50)
            out[q] = [{"entity": f.get("entity"), "predicate": f.get("predicate"), "value": f.get("value"),
                       "by": f.get("by")} for f in r.get("facts", [])] if "facts" in r else r
    except Exception as e:  # audit dump is evidence only
        out["error"] = repr(e)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", choices=["baseline", "claudemd", "plexus"], required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--plexus-url", default="http://127.0.0.1:8766")
    ap.add_argument("--max-cost", type=float, default=3.0)
    ap.add_argument("--stop-after", choices=["A", "B1", "B2"], default="B2")
    a = ap.parse_args()

    run_dir = LOGS / f"{a.arm}_{a.run_id}"
    force_rmtree(run_dir)
    run_dir.mkdir(parents=True)
    paths = setup_repos(run_dir)
    tenant = f"t7_{a.arm}_{a.run_id}_{uuid.uuid4().hex[:6]}"
    tenant = re.sub(r"[^a-z0-9_]", "_", tenant.lower())[:48]
    mcp = ({"mcpServers": {"plexus": {"type": "http", "url": f"{a.plexus_url}/mcp/t/{tenant}"}}}
           if a.arm == "plexus" else {"mcpServers": {}})
    agents = PROMPTS["agents"]
    summary = {"arm": a.arm, "run_id": a.run_id, "tenant": tenant if a.arm == "plexus" else None,
               "paths": {k: str(v) for k, v in paths.items()},
               "mangled": {k: mangle(v) for k, v in paths.items()},
               "main_sha": git(paths["main"], "rev-parse", "main"),
               "claude_code_version": subprocess.run(["claude", "--version"], capture_output=True, text=True).stdout.strip(),
               "sessions": {}, "ci_bot": None, "total_cost_usd": 0.0, "stopped": None}
    summary["projects_before"] = projects_listing(run_dir)

    def save():
        (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    for key, label, wt in SESSIONS:
        if key == "B2":
            summary["ci_bot"] = ci_bot(a.arm, paths, tenant, a.plexus_url)
            print(f"[{a.arm} {a.run_id}] ci-bot -> {summary['ci_bot']['where']}", flush=True)
            shutil.copytree(paths["main"], run_dir / "snap_main_after_cibot", ignore=SNAP_IGNORE)
        ag = agents[key]
        arm_key = "A" if key == "A" else "B"
        prompt = PROMPTS[key] + PROMPTS["arm_sentences"][a.arm][arm_key]
        res = run_session(paths[wt], prompt, ag["model"], mcp, run_dir / f"{label}.jsonl",
                          run_dir / f"scratch_data_{key}.json")
        res["agent_id"] = ag["agent_id"]
        summary["sessions"][key] = res
        summary["total_cost_usd"] = round(summary["total_cost_usd"] + res.get("cost_usd", 0.0), 4)
        shutil.copytree(paths[wt], run_dir / f"snap_{key}", ignore=SNAP_IGNORE)
        shutil.copytree(paths["main"], run_dir / f"snap_main_after_{key}", ignore=SNAP_IGNORE)
        gs = git_state(paths)
        (run_dir / f"git_state_{key}.json").write_text(json.dumps(gs, indent=2), encoding="utf-8")
        summary[f"projects_after_{key}"] = projects_listing(run_dir)
        print(f"[{a.arm} {a.run_id}] {key} ({ag['agent_id']}, {ag['model']}): rc={res['returncode']} "
              f"{res['seconds']}s ${res.get('cost_usd', 0):.3f} denials={res.get('permission_denials')} "
              f"(total ${summary['total_cost_usd']:.2f})", flush=True)
        save()
        if summary["total_cost_usd"] > a.max_cost:
            summary["stopped"] = f"over --max-cost ${a.max_cost}"
            print("STOPPED:", summary["stopped"], flush=True)
            break
        if key == a.stop_after:
            summary["stopped"] = f"--stop-after {a.stop_after}"
            break
    if a.arm == "plexus":
        summary["plexus_dump"] = plexus_dump(tenant, a.plexus_url)
    save()


if __name__ == "__main__":
    main()
