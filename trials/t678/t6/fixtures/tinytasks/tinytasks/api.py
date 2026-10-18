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
    return [t for t in load_all() if t.due_at < now and not t.archived]


def delete_task(task_id: int) -> bool:
    tasks = load_all()
    remaining = [t for t in tasks if t.id != task_id]
    save_all(remaining)
    return len(remaining) != len(tasks)


def archive_task(task_id: int) -> bool:
    """Mark a task as archived (the record stays in the data file)."""
    tasks = load_all()
    found = False
    for t in tasks:
        if t.id == task_id:
            t.archived = True
            found = True
    if found:
        save_all(tasks)
    return found
