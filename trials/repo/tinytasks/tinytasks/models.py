"""Task model. due_at is a Unix timestamp in SECONDS (not milliseconds)."""
from dataclasses import dataclass


@dataclass
class Task:
    id: int
    title: str
    due_at: float  # unix timestamp, seconds
