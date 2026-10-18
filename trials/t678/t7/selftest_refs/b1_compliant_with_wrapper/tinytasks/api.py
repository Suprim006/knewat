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


def quick_add(title):
    tasks = load_all()
    task = Task(id=next_id(tasks), title=title, due_at=int((time.time() + 86400) // 60 * 60))
    tasks.append(task)
    save_all(tasks)
    return task


def postpone_task(task_id, hours):
    tasks = load_all()
    for t in tasks:
        if t.id == task_id:
            t.due_at = (t.due_at + hours * 3600) // 60 * 60
            save_all(tasks)
            return t
    return None


def overdue_ids():
    return [t.id for t in get_overdue_tasks()]
