"""Hand-built reference implementations of the four rules for the scorer self-test.

make(root, style, c1, c2, c3, p1) copies the fixture and adds each enabled rule in the given style:
  style 'cli'   rules live in cli.py
  style 'api'   rules live in api.py (raising ValueError for the past due date)
  style 'odd'   valid-but-different variants: C3 silently ignores a past date (exit 0, task unchanged),
                C2 redacts via a helper module, P1 lowercases + dedupes, C1 filters in a helper
  style 'leaky' C1 filters stdout mode but NOT --out mode (must score NOT_ENFORCED)
  style 'broken' cli.py cannot be imported
"""
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "fixtures" / "tinytasks"


def _sub(path: Path, old: str, new: str) -> None:
    s = path.read_text(encoding="utf-8")
    assert old in s, f"patch anchor missing in {path.name}: {old[:50]!r}"
    path.write_text(s.replace(old, new, 1), encoding="utf-8")


def make(root: Path, style: str, c1=True, c2=True, c3=True, p1=True) -> Path:
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(FIXTURE, root, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    cli, api = root / "tinytasks" / "cli.py", root / "tinytasks" / "api.py"
    if style == "broken":
        cli.write_text("raise RuntimeError('broken ref')\n", encoding="utf-8")
        return root
    if style == "cli":
        if c1:
            _sub(cli, "json.dumps(export_tasks(), indent=2)",
                 "json.dumps([t for t in export_tasks() if not t.get('archived')], indent=2)")
        if c2:
            _sub(cli, "import json\n", "import json\nimport re\n")
            _sub(cli, "        t = create_task(a.title, a.due_in)",
                 "        title = re.sub(r'[\\w.+-]+@[\\w-]+(\\.[\\w-]+)+', '[email]', a.title)\n        t = create_task(title, a.due_in)")
        if c3:
            _sub(cli, "        t = reschedule_task(a.id, a.due_in)",
                 "        if a.due_in < 0:\n            raise SystemExit('error: due date is in the past')\n        t = reschedule_task(a.id, a.due_in)")
        if p1:
            _sub(cli, "        t = add_tags(a.id, a.tags)", "        t = add_tags(a.id, [x.lower() for x in a.tags])")
    elif style == "api":
        if c1:
            _sub(api, "return [dict(t.__dict__) for t in load_all()]",
                 "return [dict(t.__dict__) for t in load_all() if not t.archived]")
        if c2:
            _sub(api, "import time\n", "import re\nimport time\n")
            _sub(api, "    task = Task(id=next_id(tasks), title=title,",
                 "    title = re.sub(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\\.[A-Za-z0-9-]+)+', '[email]', title)\n"
                 "    task = Task(id=next_id(tasks), title=title,")
        if c3:
            _sub(api, "    tasks = load_all()\n    for t in tasks:\n        if t.id == task_id:\n            t.due_at = time.time()",
                 "    if due_in_seconds < 0:\n        raise ValueError('due date in the past')\n    tasks = load_all()\n    for t in tasks:\n        if t.id == task_id:\n            t.due_at = time.time()")
            _sub(cli, "        t = create_task(a.title, a.due_in)",
                 "        if a.due_in < 0:\n            raise SystemExit('error: due date is in the past')\n        t = create_task(a.title, a.due_in)")
        if p1:
            _sub(api, "            for tag in tags:\n", "            for tag in [x.lower() for x in tags]:\n")
    elif style == "odd":
        (root / "tinytasks" / "rules.py").write_text(
            "import re\n\nEMAIL = re.compile(r'\\S+@\\S+\\.\\w+')\n\n\n"
            "def redact(title):\n    return EMAIL.sub('[email]', title)\n\n\n"
            "def active(tasks):\n    return [t for t in tasks if not t.get('archived', False)]\n\n\n"
            "def norm_tags(tags):\n    seen = []\n    for t in tags:\n        t = t.strip().lower()\n        if t not in seen:\n            seen.append(t)\n    return seen\n",
            encoding="utf-8")
        _sub(cli, "import json\n", "import json\n\nfrom tinytasks import rules\n")
        if c1:
            _sub(cli, "json.dumps(export_tasks(), indent=2)", "json.dumps(rules.active(export_tasks()), indent=2)")
        if c2:
            _sub(cli, "        t = create_task(a.title, a.due_in)", "        t = create_task(rules.redact(a.title), a.due_in)")
        if c3:
            _sub(cli, "        t = reschedule_task(a.id, a.due_in)",
                 "        if a.due_in < 0:\n            print('ignored: past due date')\n            return\n        t = reschedule_task(a.id, a.due_in)")
        if p1:
            _sub(cli, "        t = add_tags(a.id, a.tags)", "        t = add_tags(a.id, rules.norm_tags(a.tags))")
    elif style == "leaky":
        _sub(cli, "        text = json.dumps(export_tasks(), indent=2)\n        if a.out:",
             "        text = json.dumps(export_tasks(), indent=2)\n        filtered = json.dumps([t for t in export_tasks() if not t.get('archived')], indent=2)\n        if a.out:")
        _sub(cli, "        else:\n            print(text)", "        else:\n            print(filtered)")
    else:
        raise ValueError(style)
    return root
