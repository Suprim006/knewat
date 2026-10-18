"""Reference exporters for the scorer self-test (hand-written). Behaviour is controlled by
tasksync/policy.py (which tasks are visible) and tasksync/timefmt.py (timestamp format)."""
import csv
import json
from pathlib import Path

from tasksync.policy import visible
from tasksync.timefmt import now_iso, to_iso


def export_json(tasks, out_path):
    rows = [{"id": t["id"], "title": t["title"], "due": to_iso(t["due_at"])} for t in visible(tasks)]
    payload = {"exported_at": now_iso(), "count": len(rows), "tasks": rows}
    Path(out_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(rows)


def export_csv(tasks, out_path):
    rows = visible(tasks)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "title", "due"])
        for t in rows:
            w.writerow([t["id"], t["title"], to_iso(t["due_at"])])
    return len(rows)


def export_md(tasks, out_path):
    rows = sorted(visible(tasks), key=lambda t: t["due_at"])
    lines = ["# Task report", "", f"Generated: {now_iso()}", "", "| id | title | due |", "|---|---|---|"]
    lines += [f"| {t['id']} | {t['title']} | {to_iso(t['due_at'])} |" for t in rows]
    Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(rows)


def webhook_payload(tasks, out_path):
    rows = [{"id": t["id"], "title": t["title"], "due": to_iso(t["due_at"])} for t in visible(tasks)]
    body = {"event": "tasks.sync", "sent_at": now_iso(), "tasks": rows}
    Path(out_path).write_text(json.dumps(body, indent=2), encoding="utf-8")
    return len(rows)
