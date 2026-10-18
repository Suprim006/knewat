import time
from datetime import datetime


def to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat()


def now_iso() -> str:
    return to_iso(time.time())
