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
