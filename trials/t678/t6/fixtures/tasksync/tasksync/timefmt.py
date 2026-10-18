"""Timestamp formatting shared by the exporters."""
from datetime import datetime


def to_iso(ts: float) -> str:
    """ISO-8601 string for a Unix timestamp given in seconds."""
    return datetime.fromtimestamp(ts).isoformat()
