"""Core task operations. due_at throughout this module is in SECONDS, matching models.Task."""
import time

from tinytasks.models import Task
from tinytasks.storage import load_all, next_id, save_all


def create_task(title: str, due_in_seconds: float) -> Task:
    """Create a task due `due_in_seconds` seconds from now."""
    tasks = load_all()
    task = Task(id=next_id(tasks), title=title, due_at=time.time() + due_in_seconds)
    tasks.append(task)
    save_all(tasks)
    return task


def get_overdue_tasks(now: float | None = None) -> list[Task]:
    """Tasks whose due_at (seconds) has already passed."""
    now = now if now is not None else time.time()
    return [t for t in load_all() if t.due_at < now]


def delete_task(task_id: int) -> bool:
    tasks = load_all()
    remaining = [t for t in tasks if t.id != task_id]
    save_all(remaining)
    return len(remaining) != len(tasks)


def archive_task(task_id: int) -> bool:
    """Mark a task archived (the record is kept)."""
    tasks = load_all()
    found = False
    for t in tasks:
        if t.id == task_id:
            t.archived = True
            found = True
    save_all(tasks)
    return found


def reschedule_task(task_id: int, due_in_seconds: float) -> Task | None:
    """Move a task's due date to `due_in_seconds` seconds from now."""
    tasks = load_all()
    for t in tasks:
        if t.id == task_id:
            t.due_at = time.time() + due_in_seconds
            save_all(tasks)
            return t
    return None


def add_tags(task_id: int, tags: list[str]) -> Task | None:
    """Attach tags to a task."""
    tasks = load_all()
    for t in tasks:
        if t.id == task_id:
            for tag in tags:
                if tag not in t.tags:
                    t.tags.append(tag)
            save_all(tasks)
            return t
    return None


def export_tasks() -> list[dict]:
    """All tasks as plain dicts, for handing to other systems."""
    return [dict(t.__dict__) for t in load_all()]
