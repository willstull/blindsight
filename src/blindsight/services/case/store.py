"""DuckDB case store lifecycle: open/create, schema migration, case CRUD."""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb

from blindsight.services.case.json_helpers import to_json, from_json
from blindsight.types.result import Result, Ok, Err
from blindsight.utils.ulid import generate_ulid

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"

CURRENT_SCHEMA_VERSION = 3

# Paths where ensure_schema has already succeeded, skipping redundant migration checks.
_verified_paths: set[str] = set()


def _discover_migrations() -> list[tuple[int, Path]]:
    """Discover migration SQL files in version order.

    Files must match NNN_*.sql pattern. Returns (version, path) pairs
    sorted by version number.
    """
    migrations = []
    for path in sorted(_MIGRATIONS_DIR.glob("*.sql")):
        parts = path.stem.split("_", 1)
        if parts[0].isdigit():
            migrations.append((int(parts[0]), path))
    return migrations


def ensure_schema(logger: logging.Logger, conn: duckdb.DuckDBPyConnection) -> Result[int, Exception]:
    """Check schema_migrations and apply pending migrations. Returns current version."""
    try:
        # Check if schema_migrations table exists
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'schema_migrations'"
        ).fetchall()

        if tables:
            rows = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            current_version = rows[0] if rows and rows[0] is not None else 0
        else:
            current_version = 0

        for version, path in _discover_migrations():
            if current_version < version:
                logger.info(
                    "Applying migration",
                    extra={"version": version, "file": path.name, "from_version": current_version},
                )
                sql = path.read_text()
                conn.execute(sql)
                current_version = version

        return Ok(current_version)
    except Exception as e:
        logger.error("Schema migration failed", extra={"error": str(e)})
        return Err(e)


def open_case_db(logger: logging.Logger, db_path: Path) -> Result[duckdb.DuckDBPyConnection, Exception]:
    """Open (or create) a case database and ensure schema is current."""
    try:
        conn = duckdb.connect(str(db_path))
        path_key = str(db_path)
        if path_key not in _verified_paths:
            schema_result = ensure_schema(logger, conn)
            if schema_result.is_err():
                conn.close()
                return Err(schema_result.err())
            _verified_paths.add(path_key)
            logger.info("Case DB opened", extra={"path": path_key, "schema_version": schema_result.ok()})
        else:
            logger.info("Case DB opened (schema cached)", extra={"path": path_key})
        return Ok(conn)
    except Exception as e:
        logger.error("Failed to open case DB", extra={"path": str(db_path), "error": str(e)})
        return Err(e)


def create_case(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    case_id: str,
    title: str,
    tlp: str = "GREEN",
    severity: str = "sev3",
    tags: Optional[list[str]] = None,
) -> Result[dict, Exception]:
    """Insert a new case record. Returns the case as a dict."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO cases (id, tlp, title, status, severity, created_at, tags, updated_at)
               VALUES (?, ?, ?, 'new', ?, ?, ?, ?)""",
            [case_id, tlp, title, severity, now, to_json(tags or []), now],
        )
        logger.info("Case created", extra={"case_id": case_id, "title": title})
        return get_case(logger, conn, case_id)
    except Exception as e:
        logger.error("Failed to create case", extra={"case_id": case_id, "error": str(e)})
        return Err(e)


def get_case(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    case_id: str,
) -> Result[Optional[dict], Exception]:
    """Fetch a case by ID. Returns None if not found."""
    try:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", [case_id]).fetchone()
        if row is None:
            return Ok(None)
        columns = [desc[0] for desc in conn.description]
        case = dict(zip(columns, row))
        # Parse JSON columns
        for col in ("hypothesis_ids", "tags", "investigation_metadata"):
            if col in case:
                case[col] = from_json(case[col])
        # Convert timestamps to strings
        for col in ("created_at", "detected_at", "contained_at", "resolved_at", "updated_at"):
            if col in case and case[col] is not None:
                case[col] = str(case[col])
        return Ok(case)
    except Exception as e:
        logger.error("Failed to get case", extra={"case_id": case_id, "error": str(e)})
        return Err(e)


def update_case_metadata(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    case_id: str,
    metadata: dict,
) -> Result[bool, Exception]:
    """Update investigation_metadata JSON column on a case. Returns True on success."""
    try:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE cases SET investigation_metadata = ?, updated_at = ? WHERE id = ?",
            [to_json(metadata), now, case_id],
        )
        logger.info("Updated case metadata", extra={"case_id": case_id})
        return Ok(True)
    except Exception as e:
        logger.error("Failed to update case metadata", extra={"case_id": case_id, "error": str(e)})
        return Err(e)
