"""Correlation queries against the case store."""
import logging
from typing import Optional

import duckdb

from src.services.case.json_helpers import from_json
from src.types.result import Result, Ok, Err

# JSON columns per table that need from_json() parsing
_ENTITY_JSON_COLS = ("refs", "attributes")
EVENT_JSON_COLS = ("actor", "targets", "raw_refs", "context", "related_entity_ids")
_RELATIONSHIP_JSON_COLS = ("evidence_refs",)
_TOOL_CALL_JSON_COLS = ("request_params", "response_body")

MAX_LIMIT = 2000


def rows_to_dicts(conn: duckdb.DuckDBPyConnection, rows: list, json_cols: tuple) -> list[dict]:
    """Convert raw rows to dicts, parsing JSON columns and stringifying timestamps."""
    columns = [desc[0] for desc in conn.description]
    results = []
    for row in rows:
        d = dict(zip(columns, row))
        for col in json_cols:
            if col in d:
                d[col] = from_json(d[col])
        # Convert datetime objects to strings
        for col in columns:
            if col in d and d[col] is not None and hasattr(d[col], 'isoformat'):
                d[col] = str(d[col])
        results.append(d)
    return results


def query_entities(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    entity_types: Optional[list[str]] = None,
    kinds: Optional[list[str]] = None,
    display_name_contains: Optional[str] = None,
    limit: int = 100,
) -> Result[list[dict], Exception]:
    """Query entities with optional filters."""
    try:
        clauses = []
        params = []

        if entity_types:
            placeholders = ", ".join(["?"] * len(entity_types))
            clauses.append(f"entity_type IN ({placeholders})")
            params.extend(entity_types)

        if kinds:
            placeholders = ", ".join(["?"] * len(kinds))
            clauses.append(f"kind IN ({placeholders})")
            params.extend(kinds)

        if display_name_contains:
            clauses.append("display_name ILIKE ?")
            params.append(f"%{display_name_contains}%")

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        effective_limit = min(limit, MAX_LIMIT)
        params.append(effective_limit)

        sql = f"SELECT * FROM entities {where} ORDER BY display_name LIMIT ?"
        rows = conn.execute(sql, params).fetchall()
        return Ok(rows_to_dicts(conn, rows, _ENTITY_JSON_COLS))
    except Exception as e:
        logger.error("Entity query failed", extra={"error": str(e)})
        return Err(e)


def query_events(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    actor_entity_id: Optional[str] = None,
    target_entity_id: Optional[str] = None,
    actions: Optional[list[str]] = None,
    time_range_start: Optional[str] = None,
    time_range_end: Optional[str] = None,
    outcome: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 100,
) -> Result[list[dict], Exception]:
    """Query events with optional filters."""
    try:
        clauses = []
        params = []

        if actor_entity_id:
            clauses.append("json_extract_string(actor, '$.actor_entity_id') = ?")
            params.append(actor_entity_id)

        if target_entity_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM json_each(targets) t "
                "WHERE json_extract_string(t.value, '$.target_entity_id') = ?)"
            )
            params.append(target_entity_id)

        if actions:
            exact = [a for a in actions if not a.endswith("*")]
            prefixes = [a[:-1] for a in actions if a.endswith("*")]
            action_parts = []
            if exact:
                placeholders = ", ".join(["?"] * len(exact))
                action_parts.append(f"action IN ({placeholders})")
                params.extend(exact)
            for prefix in prefixes:
                action_parts.append("action LIKE ?")
                params.append(f"{prefix}%")
            if action_parts:
                clauses.append(f"({' OR '.join(action_parts)})")

        if time_range_start:
            clauses.append("ts >= ?::TIMESTAMP")
            params.append(time_range_start)

        if time_range_end:
            clauses.append("ts <= ?::TIMESTAMP")
            params.append(time_range_end)

        if outcome:
            clauses.append("outcome = ?")
            params.append(outcome)

        if domain:
            clauses.append("domain = ?")
            params.append(domain)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        effective_limit = min(limit, MAX_LIMIT)
        params.append(effective_limit)

        sql = f"SELECT * FROM events {where} ORDER BY ts DESC LIMIT ?"
        rows = conn.execute(sql, params).fetchall()
        return Ok(rows_to_dicts(conn, rows, EVENT_JSON_COLS))
    except Exception as e:
        logger.error("Event query failed", extra={"error": str(e)})
        return Err(e)


def query_neighbors(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    entity_id: str,
    relationship_types: Optional[list[str]] = None,
    limit: int = 100,
) -> Result[list[dict], Exception]:
    """Find entities connected to entity_id via relationships (bidirectional)."""
    try:
        type_filter = ""
        params: list = [entity_id, entity_id, entity_id]

        if relationship_types:
            placeholders = ", ".join(["?"] * len(relationship_types))
            type_filter = f"AND r.relationship_type IN ({placeholders})"
            params.extend(relationship_types)

        effective_limit = min(limit, MAX_LIMIT)
        params.append(effective_limit)

        sql = f"""
            SELECT e.*, r.id AS relationship_id, r.relationship_type,
                   CASE WHEN r.from_entity_id = ? THEN 'outgoing' ELSE 'incoming' END AS direction
            FROM entities e
            JOIN relationships r ON (
                (r.to_entity_id = e.id AND r.from_entity_id = ?)
                OR (r.from_entity_id = e.id AND r.to_entity_id = ?)
            )
            WHERE 1=1 {type_filter}
            LIMIT ?
        """
        rows = conn.execute(sql, params).fetchall()
        # Parse with extended columns
        columns = [desc[0] for desc in conn.description]
        results = []
        for row in rows:
            d = dict(zip(columns, row))
            for col in _ENTITY_JSON_COLS:
                if col in d:
                    d[col] = from_json(d[col])
            for col in columns:
                if col in d and d[col] is not None and hasattr(d[col], 'isoformat'):
                    d[col] = str(d[col])
            results.append(d)

        return Ok(results)
    except Exception as e:
        logger.error("Neighbor query failed", extra={"error": str(e)})
        return Err(e)


def get_timeline(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    time_range_start: Optional[str] = None,
    time_range_end: Optional[str] = None,
    actor_entity_id: Optional[str] = None,
    limit: int = 100,
) -> Result[list[dict], Exception]:
    """Get events ordered chronologically (ascending) for timeline view."""
    try:
        clauses = []
        params = []

        if time_range_start:
            clauses.append("ts >= ?::TIMESTAMP")
            params.append(time_range_start)

        if time_range_end:
            clauses.append("ts <= ?::TIMESTAMP")
            params.append(time_range_end)

        if actor_entity_id:
            clauses.append("json_extract_string(actor, '$.actor_entity_id') = ?")
            params.append(actor_entity_id)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        effective_limit = min(limit, MAX_LIMIT)
        params.append(effective_limit)

        sql = f"SELECT * FROM events {where} ORDER BY ts ASC LIMIT ?"
        rows = conn.execute(sql, params).fetchall()
        return Ok(rows_to_dicts(conn, rows, EVENT_JSON_COLS))
    except Exception as e:
        logger.error("Timeline query failed", extra={"error": str(e)})
        return Err(e)


def get_tool_call_history(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    case_id: str,
    limit: int = 100,
) -> Result[list[dict], Exception]:
    """Get tool call history for a case, most recent first."""
    try:
        effective_limit = min(limit, MAX_LIMIT)
        rows = conn.execute(
            "SELECT * FROM tool_calls WHERE case_id = ? ORDER BY executed_at DESC LIMIT ?",
            [case_id, effective_limit],
        ).fetchall()
        return Ok(rows_to_dicts(conn, rows, _TOOL_CALL_JSON_COLS))
    except Exception as e:
        logger.error("Tool call history query failed", extra={"error": str(e)})
        return Err(e)
