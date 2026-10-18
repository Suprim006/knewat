"""Task model. due_at is a Unix timestamp in SECONDS (not milliseconds)."""
from dataclasses import dataclass, field


@dataclass
class Task:
    id: int
    title: str
    due_at: float  # unix timestamp, seconds
    archived: bool = False
    tags: list[str] = field(default_factory=list)
