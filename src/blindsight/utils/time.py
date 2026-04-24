"""Time parsing and comparison utilities."""
from datetime import datetime, timezone


def parse_rfc3339(ts: str) -> datetime:
    """Parse an RFC3339 timestamp string to datetime."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def is_within_range(ts: str, start: str, end: str) -> bool:
    """Check whether ts falls within [start, end] inclusive."""
    ts_dt = parse_rfc3339(ts)
    start_dt = parse_rfc3339(start)
    end_dt = parse_rfc3339(end)
    return start_dt <= ts_dt <= end_dt


def within_minutes(ts1: str, ts2: str, minutes: int) -> bool:
    """Check if two ISO timestamps are within N minutes of each other."""
    try:
        t1 = parse_rfc3339(ts1)
        t2 = parse_rfc3339(ts2)
        return abs((t2 - t1).total_seconds()) <= minutes * 60
    except (ValueError, TypeError):
        return False
