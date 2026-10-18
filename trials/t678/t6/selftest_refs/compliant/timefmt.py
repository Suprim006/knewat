import time
from datetime import datetime, timezone


def to_iso(ts: float) -> str:
    """X2: UTC ISO-8601 with a Z suffix."""
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return to_iso(time.time())
