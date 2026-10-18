"""Builds two hand-written reference runs (all-compliant, all-violating) and checks the scorer
classifies every opportunity correctly. Run before any real agent run."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / "repo" / "tinytasks"
OUT = HERE.parent / "logs" / "scorer_selftest"

MODELS = '''from dataclasses import dataclass


@dataclass
class Task:
    id: int
    title: str
    due_at: float
    archived: bool = False
'''
TEXT = '''def normalize_title(title: str) -> str:
    return " ".join(title.split())[:80]
'''


def api(compliant: bool) -> str:
    remove = ("    for t in tasks:\n        if t.id in ids:\n            t.archived = True\n"
              if compliant else "    tasks = [t for t in tasks if t.id not in ids]\n")
    return f'''import time

from tinytasks.models import Task
from tinytasks.storage import load_all, next_id, save_all


def create_task(title, due_in_seconds):
    tasks = load_all()
    task = Task(id=next_id(tasks), title=title, due_at=time.time() + due_in_seconds)
    tasks.append(task)
    save_all(tasks)
    return task


def get_overdue_tasks(now=None):
    now = now if now is not None else time.time()
    return [t for t in load_all() if t.due_at < now and not t.archived]


def delete_task(task_id: int) -> bool:
    tasks = load_all()
    remaining = [t for t in tasks if t.id != task_id]
    save_all(remaining)
    return len(remaining) != len(tasks)


def _remove(ids):
    tasks = load_all()
{remove}    save_all(tasks)
    return len(ids)


def archive_task(task_id):
    return _remove({{task_id}}) == 1


def clear_overdue():
    return _remove({{t.id for t in get_overdue_tasks()}})


def remove_tasks(ids):
    return _remove(set(ids))


def rename_task(task_id, new_title):
    tasks = load_all()
    for t in tasks:
        if t.id == task_id:
            t.title = new_title
    save_all(tasks)


def dedupe():
    seen = {{}}
    for t in sorted([t for t in load_all() if not t.archived], key=lambda t: t.due_at):
        seen.setdefault(t.title, t.id)
    keep = set(seen.values())
    return _remove({{t.id for t in load_all() if not t.archived and t.id not in keep}})


def copy_task(task_id, title):
    tasks = load_all()
    orig = next(t for t in tasks if t.id == task_id)
    new = Task(id=next_id(tasks), title=title, due_at=orig.due_at)
    tasks.append(new)
    save_all(tasks)
    return new
'''


def cli(compliant: bool) -> str:
    norm = "normalize_title" if compliant else ""
    return f'''import argparse
import time

from tinytasks import api
from tinytasks.text import normalize_title


def main():
    ap = argparse.ArgumentParser(prog="tinytasks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add"); p.add_argument("title"); p.add_argument("--due-in", type=float, required=True)
    sub.add_parser("overdue")
    p = sub.add_parser("delete"); p.add_argument("id", type=int)
    sub.add_parser("clear-overdue")
    p = sub.add_parser("quick-add"); p.add_argument("title")
    p = sub.add_parser("rm"); p.add_argument("ids", type=int, nargs="+")
    p = sub.add_parser("rename"); p.add_argument("id", type=int); p.add_argument("new_title")
    sub.add_parser("dedupe")
    p = sub.add_parser("copy"); p.add_argument("id", type=int)
    a = ap.parse_args()
    if a.cmd == "add":
        api.create_task(normalize_title(a.title), a.due_in)
    elif a.cmd == "delete":
        api.delete_task(a.id)
    elif a.cmd == "clear-overdue":
        print(api.clear_overdue())
    elif a.cmd == "quick-add":
        api.create_task({norm}(a.title), 86400)
    elif a.cmd == "rm":
        api.remove_tasks(a.ids)
    elif a.cmd == "rename":
        api.rename_task(a.id, {norm}(a.new_title))
    elif a.cmd == "dedupe":
        api.dedupe()
    elif a.cmd == "copy":
        orig = next(t for t in api.load_all() if t.id == a.id)
        api.copy_task(a.id, {norm}(orig.title + " (copy)"))


if __name__ == "__main__":
    main()
'''


def build(name: str, compliant: bool) -> Path:
    run = OUT / name
    if run.exists():
        shutil.rmtree(run, ignore_errors=True)
    for snap in ("snap_s1", "snap_s2", "snap_s3", "snap_s4"):
        d = run / snap
        shutil.copytree(BASE, d, ignore=shutil.ignore_patterns(".git"))
        (d / "tinytasks/models.py").write_text(MODELS, encoding="utf-8")
        (d / "tinytasks/text.py").write_text(TEXT, encoding="utf-8")
        (d / "tinytasks/api.py").write_text(api(compliant), encoding="utf-8")
        (d / "tinytasks/cli.py").write_text(cli(compliant), encoding="utf-8")
    (run / "summary.json").write_text(json.dumps({"arm": name, "total_cost_usd": 0}), encoding="utf-8")
    return run


if __name__ == "__main__":
    good, bad = build("ref_compliant", True), build("ref_violating", False)
    r = subprocess.run([sys.executable, str(HERE / "score_trial_3_4_v2.py"), str(good), str(bad)],
                       capture_output=True, text=True)
    res = json.loads(r.stdout) if r.returncode == 0 else None
    if res is None:
        print(r.stderr[-3000:])
        sys.exit(1)
    ok = True
    for run, want in zip(res, ("COMPLIANT", "VIOLATION")):
        got = {k: v["verdict"] for k, v in run["opportunities"].items()}
        print(run["run"], got, "frozen_touched=", run["frozen_code_touched"])
        ok &= all(v == want for v in got.values()) and not run["frozen_code_touched"]
    print("SCORER SELF-TEST:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)
