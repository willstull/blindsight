"""DuckDB case store lifecycle: open/create, schema migration, case CRUD."""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import duckdb

from src.services.case.json_helpers import to_json, from_json
from src.types.result import Result, Ok, Err
from src.utils.ulid import generate_ulid

CURRENT_SCHEMA_VERSION = 2

# Paths where ensure_schema has already succeeded, skipping redundant migration checks.
_verified_paths: set[str] = set()

MIGRATION_001 = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    description VARCHAR NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Cases
CREATE TABLE IF NOT EXISTS cases (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL,
    detected_at TIMESTAMP,
    contained_at TIMESTAMP,
    resolved_at TIMESTAMP,
    mttd_seconds DOUBLE,
    mttc_seconds DOUBLE,
    mttr_seconds DOUBLE,
    hypothesis_ids JSON,
    tags JSON,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS idx_cases_severity ON cases(severity);

-- Entities
CREATE TABLE IF NOT EXISTS entities (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    refs JSON,
    attributes JSON,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    confidence DOUBLE,
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_entities_type_kind ON entities(entity_type, kind);
CREATE INDEX IF NOT EXISTS idx_entities_display_name ON entities(display_name);

-- Events
CREATE TABLE IF NOT EXISTS events (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    domain VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL,
    action VARCHAR NOT NULL,
    actor JSON NOT NULL,
    targets JSON NOT NULL,
    outcome VARCHAR NOT NULL,
    raw_refs JSON NOT NULL,
    context JSON,
    related_entity_ids JSON,
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_domain_action ON events(domain, action);

-- Relationships
CREATE TABLE IF NOT EXISTS relationships (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    domain VARCHAR NOT NULL,
    relationship_type VARCHAR NOT NULL,
    from_entity_id VARCHAR NOT NULL,
    to_entity_id VARCHAR NOT NULL,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    evidence_refs JSON,
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_to ON relationships(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(relationship_type);

-- Coverage reports
CREATE TABLE IF NOT EXISTS coverage_reports (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    domain VARCHAR NOT NULL,
    time_range_start TIMESTAMP NOT NULL,
    time_range_end TIMESTAMP NOT NULL,
    overall_status VARCHAR NOT NULL,
    sources JSON NOT NULL,
    missing_fields JSON,
    data_latency_seconds DOUBLE,
    quality_flags JSON,
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_coverage_domain_time ON coverage_reports(domain, time_range_start, time_range_end);

-- Evidence items (analysis table -- tools deferred)
CREATE TABLE IF NOT EXISTS evidence_items (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    domain VARCHAR NOT NULL,
    summary TEXT NOT NULL,
    raw_refs JSON NOT NULL,
    collected_at TIMESTAMP NOT NULL,
    related_entity_ids JSON,
    related_event_ids JSON,
    hash VARCHAR,
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_evidence_domain ON evidence_items(domain);
CREATE INDEX IF NOT EXISTS idx_evidence_collected ON evidence_items(collected_at);

-- Claims (analysis table -- tools deferred)
CREATE TABLE IF NOT EXISTS claims (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    statement TEXT NOT NULL,
    polarity VARCHAR NOT NULL,
    confidence DOUBLE NOT NULL,
    backed_by_evidence_ids JSON NOT NULL,
    subject_entity_ids JSON,
    time_range_start TIMESTAMP,
    time_range_end TIMESTAMP,
    derived_from_claim_ids JSON,
    assumption_ids JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_claims_confidence ON claims(confidence);
CREATE INDEX IF NOT EXISTS idx_claims_polarity ON claims(polarity);

-- Assumptions (analysis table -- tools deferred)
CREATE TABLE IF NOT EXISTS assumptions (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    statement TEXT NOT NULL,
    strength VARCHAR NOT NULL,
    rationale TEXT NOT NULL,
    impacts JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Hypotheses (analysis table -- tools deferred)
CREATE TABLE IF NOT EXISTS hypotheses (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    iq_id VARCHAR NOT NULL,
    statement TEXT NOT NULL,
    likelihood_score DOUBLE NOT NULL,
    confidence_cap DOUBLE NOT NULL,
    supporting_claim_ids JSON NOT NULL,
    contradicting_claim_ids JSON,
    gaps JSON NOT NULL,
    next_evidence_requests JSON NOT NULL,
    status VARCHAR,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_hypotheses_iq ON hypotheses(iq_id);
CREATE INDEX IF NOT EXISTS idx_hypotheses_status ON hypotheses(status);

-- Tool calls
CREATE TABLE IF NOT EXISTS tool_calls (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL,
    domain VARCHAR NOT NULL,
    tool_name VARCHAR NOT NULL,
    request_params JSON NOT NULL,
    response_status VARCHAR NOT NULL,
    response_body JSON NOT NULL,
    coverage_report_id VARCHAR,
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tool_calls_case ON tool_calls(case_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_request ON tool_calls(request_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_executed ON tool_calls(executed_at);

-- Record migration
INSERT INTO schema_migrations (version, description, applied_at)
VALUES (1, 'Initial schema: 11 tables', CURRENT_TIMESTAMP);
"""


MIGRATION_002 = """
CREATE TABLE IF NOT EXISTS investigation_pivots (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL,
    label VARCHAR NOT NULL,
    description TEXT,
    event_ids JSON NOT NULL,
    entity_ids JSON NOT NULL,
    relationship_ids JSON NOT NULL,
    focal_entity_ids JSON,
    time_range_start TIMESTAMP,
    time_range_end TIMESTAMP,
    coverage_report_ids JSON,
    created_from_tool_call_ids JSON,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pivots_case ON investigation_pivots(case_id);
CREATE INDEX IF NOT EXISTS idx_pivots_created ON investigation_pivots(created_at);

INSERT INTO schema_migrations (version, description, applied_at)
VALUES (2, 'Add investigation_pivots table', CURRENT_TIMESTAMP);
"""


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

        if current_version < 1:
            logger.info("Applying migration v001", extra={"from_version": current_version})
            conn.execute(MIGRATION_001)
            current_version = 1

        if current_version < 2:
            logger.info("Applying migration v002", extra={"from_version": current_version})
            conn.execute(MIGRATION_002)
            current_version = 2

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
        for col in ("hypothesis_ids", "tags"):
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
