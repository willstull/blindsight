"""Investigation pivot CRUD, timeline, and clustering queries."""
import collections
import logging

import duckdb

from src.services.case.json_helpers import to_json, from_json
from src.services.case.query import rows_to_dicts, EVENT_JSON_COLS, MAX_LIMIT
from src.types.result import Result, Ok, Err
from src.utils.time import within_minutes


_PIVOT_JSON_COLS = (
    "event_ids", "entity_ids", "relationship_ids",
    "focal_entity_ids", "coverage_report_ids", "created_from_tool_call_ids",
)


def _parse_pivot_row(conn: duckdb.DuckDBPyConnection, row: tuple) -> dict:
    """Convert a raw pivot row to a dict with parsed JSON and string timestamps."""
    columns = [desc[0] for desc in conn.description]
    d = dict(zip(columns, row))
    for col in _PIVOT_JSON_COLS:
        if col in d:
            d[col] = from_json(d[col])
    for col in ("time_range_start", "time_range_end", "created_at"):
        if col in d and d[col] is not None and hasattr(d[col], "isoformat"):
            d[col] = str(d[col])
    return d


def save_pivot(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    pivot_id: str,
    case_id: str,
    label: str,
    description: str | None,
    event_ids: list[str],
    entity_ids: list[str],
    relationship_ids: list[str],
    focal_entity_ids: list[str] | None = None,
    coverage_report_ids: list[str] | None = None,
    created_from_tool_call_ids: list[str] | None = None,
) -> Result[dict, Exception]:
    """Save an investigation pivot. Returns the saved pivot dict."""
    try:
        if not event_ids and not entity_ids and not relationship_ids:
            return Err(ValueError("At least one of event_ids, entity_ids, or relationship_ids must be non-empty"))

        # Compute time range from events
        time_range_start = None
        time_range_end = None
        if event_ids:
            query_ids = event_ids[:MAX_LIMIT]
            if len(event_ids) > MAX_LIMIT:
                logger.warning(
                    "Pivot event_ids truncated for IN clause",
                    extra={"pivot_id": pivot_id, "total": len(event_ids), "cap": MAX_LIMIT},
                )
            placeholders = ", ".join(["?"] * len(query_ids))
            result = conn.execute(
                f"SELECT MIN(ts), MAX(ts), COUNT(*) FROM events WHERE id IN ({placeholders})",
                query_ids,
            ).fetchone()
            if result and result[0] is not None:
                time_range_start = result[0]
                time_range_end = result[1]
                found_count = result[2]
                if found_count != len(event_ids):
                    logger.warning(
                        "Pivot event count mismatch",
                        extra={
                            "pivot_id": pivot_id,
                            "expected": len(event_ids),
                            "found": found_count,
                        },
                    )

        conn.execute(
            """INSERT INTO investigation_pivots
               (id, case_id, label, description, event_ids, entity_ids,
                relationship_ids, focal_entity_ids, time_range_start,
                time_range_end, coverage_report_ids, created_from_tool_call_ids)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                pivot_id, case_id, label, description,
                to_json(event_ids), to_json(entity_ids), to_json(relationship_ids),
                to_json(focal_entity_ids), time_range_start, time_range_end,
                to_json(coverage_report_ids), to_json(created_from_tool_call_ids),
            ],
        )
        logger.info("Pivot saved", extra={"pivot_id": pivot_id, "label": label})
        return get_pivot(logger, conn, pivot_id)
    except Exception as e:
        logger.error("Failed to save pivot", extra={"pivot_id": pivot_id, "error": str(e)})
        return Err(e)


def list_pivots(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    case_id: str,
) -> Result[list[dict], Exception]:
    """List all pivots for a case, ordered by creation time."""
    try:
        rows = conn.execute(
            "SELECT * FROM investigation_pivots WHERE case_id = ? ORDER BY created_at",
            [case_id],
        ).fetchall()
        results = []
        for row in rows:
            d = _parse_pivot_row(conn, row)
            d["event_count"] = len(d.get("event_ids") or [])
            d["entity_count"] = len(d.get("entity_ids") or [])
            d["relationship_count"] = len(d.get("relationship_ids") or [])
            results.append(d)
        return Ok(results)
    except Exception as e:
        logger.error("Failed to list pivots", extra={"case_id": case_id, "error": str(e)})
        return Err(e)


def get_pivot(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    pivot_id: str,
) -> Result[dict | None, Exception]:
    """Fetch a single pivot by ID."""
    try:
        row = conn.execute(
            "SELECT * FROM investigation_pivots WHERE id = ?",
            [pivot_id],
        ).fetchone()
        if row is None:
            return Ok(None)
        return Ok(_parse_pivot_row(conn, row))
    except Exception as e:
        logger.error("Failed to get pivot", extra={"pivot_id": pivot_id, "error": str(e)})
        return Err(e)


def _fetch_pivot_events(
    conn: duckdb.DuckDBPyConnection,
    logger: logging.Logger,
    pivot_id: str,
    limit: int | None = None,
) -> tuple[dict | None, list[dict]]:
    """Fetch a pivot and its events. Returns (pivot_dict, events_list)."""
    result = get_pivot(logger, conn, pivot_id)
    if result.is_err():
        return None, []
    pivot = result.ok()
    if pivot is None:
        return None, []

    event_ids = pivot.get("event_ids") or []
    if not event_ids:
        return pivot, []

    query_ids = event_ids[:MAX_LIMIT]
    placeholders = ", ".join(["?"] * len(query_ids))
    sql = f"SELECT * FROM events WHERE id IN ({placeholders}) ORDER BY ts ASC"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql, query_ids).fetchall()
    events = rows_to_dicts(conn, rows, EVENT_JSON_COLS)
    return pivot, events


def query_pivot_timeline(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    pivot_id: str,
    limit: int = 100,
) -> Result[list[dict], Exception]:
    """Get events belonging to a pivot, ordered chronologically."""
    try:
        pivot, events = _fetch_pivot_events(conn, logger, pivot_id, limit=limit)
        if pivot is None:
            return Err(ValueError("Pivot not found"))
        return Ok(events)
    except Exception as e:
        logger.error("Failed to query pivot timeline", extra={"pivot_id": pivot_id, "error": str(e)})
        return Err(e)


def find_event_clusters(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    pivot_id: str,
    window_minutes: int = 10,
    min_events: int = 3,
) -> Result[list[dict], Exception]:
    """Find temporal clusters of events within a pivot."""
    try:
        pivot, events = _fetch_pivot_events(conn, logger, pivot_id)
        if pivot is None:
            return Err(ValueError("Pivot not found"))

        if not events:
            return Ok([])

        # Sliding-window clustering
        clusters: list[list[dict]] = []
        current_cluster: list[dict] = [events[0]]

        for evt in events[1:]:
            prev_ts = current_cluster[-1].get("ts", "")
            curr_ts = evt.get("ts", "")
            if within_minutes(prev_ts, curr_ts, window_minutes):
                current_cluster.append(evt)
            else:
                if len(current_cluster) >= min_events:
                    clusters.append(current_cluster)
                current_cluster = [evt]

        if len(current_cluster) >= min_events:
            clusters.append(current_cluster)

        result = []
        for i, cluster in enumerate(clusters):
            actions = [e.get("action", "?") for e in cluster]
            counter = collections.Counter(actions)
            result.append({
                "cluster_id": i,
                "start": cluster[0].get("ts", ""),
                "end": cluster[-1].get("ts", ""),
                "event_count": len(cluster),
                "event_ids": [e.get("id", "") for e in cluster],
                "dominant_actions": [a for a, _ in counter.most_common()],
            })

        return Ok(result)
    except Exception as e:
        logger.error("Failed to find event clusters", extra={"pivot_id": pivot_id, "error": str(e)})
        return Err(e)
