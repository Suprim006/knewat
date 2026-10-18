"""Read-only task queries."""
from tinytasks.models import Task
from tinytasks.storage import load_all


def tasks_due_before(cutoff: float) -> list[Task]:
    """Tasks whose due_at (seconds) is strictly before `cutoff` (a Unix timestamp in seconds)."""
    return [t for t in load_all() if t.due_at < cutoff]
