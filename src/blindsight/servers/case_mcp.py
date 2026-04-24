"""Case store MCP server.

Exposes case management and correlation query tools via FastMCP.
Each tool opens the case DB, performs the operation, and closes in finally.
"""
import logging
import re
import sys
from pathlib import Path
from typing import Optional

from mcp.server import FastMCP

from src.services.case.store import open_case_db, create_case, get_case
from src.services.case.ingest import ingest_domain_response, record_tool_call
from src.services.case.query import (
    query_entities, query_events, query_neighbors,
    get_timeline, get_tool_call_history, get_report_facts,
)
from src.types.core import CoverageReport, TimeRange, SourceStatus
from src.utils.ulid import generate_ulid


_CASE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

_CASE_COVERAGE_REPORT = CoverageReport(
    id="case-store-coverage",
    tlp="GREEN",
    domain="case",
    time_range=TimeRange(start="1970-01-01T00:00:00Z", end="2099-12-31T23:59:59Z"),
    overall_status="complete",
    sources=[SourceStatus(
        source_name="case_store",
        status="complete",
        notes="Reflects only data ingested into this case",
    )],
    notes="Coverage reflects ingested case data only, not upstream source completeness",
)
_CASE_COVERAGE_DICT = _CASE_COVERAGE_REPORT.model_dump(exclude_none=True)


def _validate_case_id(case_id: str) -> str | None:
    """Return an error message if case_id is invalid, else None."""
    if not _CASE_ID_PATTERN.match(case_id):
        return f"Invalid case_id: must match [a-zA-Z0-9_-]{{1,128}}, got '{case_id}'"
    return None


def _success_envelope(
    request_id: str,
    *,
    entities: list | None = None,
    events: list | None = None,
    relationships: list | None = None,
    results: list | None = None,
) -> dict:
    envelope: dict = {
        "status": "success",
        "domain": "case",
        "request_id": request_id,
        "coverage_report": _CASE_COVERAGE_DICT,
    }
    if entities is not None:
        envelope["entities"] = entities
    if events is not None:
        envelope["events"] = events
    if relationships is not None:
        envelope["relationships"] = relationships
    if results is not None:
        envelope["results"] = results
    return envelope


def _error_envelope(request_id: str, code: str, message: str) -> dict:
    return {
        "status": "error",
        "domain": "case",
        "request_id": request_id,
        "coverage_report": _CASE_COVERAGE_DICT,
        "error": {"code": code, "message": message, "severity": "error"},
    }


def _db_path_for_case(cases_dir: Path, case_id: str) -> Path:
    return cases_dir / f"{case_id}.duckdb"


def create_case_server(cases_dir: Path, logger: logging.Logger) -> FastMCP:
    """Create and configure the case store MCP server."""
    cases_dir.mkdir(parents=True, exist_ok=True)
    server = FastMCP("blindsight-case-mcp")

    @server.tool()
    async def create_case_tool(
        title: str,
        tlp: str = "GREEN",
        severity: str = "sev3",
        tags: list[str] | None = None,
    ) -> dict:
        """Create a new investigation case. Returns the case record."""
        request_id = generate_ulid()
        case_id = generate_ulid()
        db_path = _db_path_for_case(cases_dir, case_id)

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = create_case(logger, conn, case_id, title, tlp, severity, tags)
            if result.is_err():
                return _error_envelope(request_id, "create_case_failed", str(result.err()))
            return _success_envelope(request_id, results=[result.ok()])
        finally:
            conn.close()

    @server.tool()
    async def get_case_tool(case_id: str) -> dict:
        """Fetch a case by ID."""
        request_id = generate_ulid()
        err = _validate_case_id(case_id)
        if err:
            return _error_envelope(request_id, "invalid_case_id", err)

        db_path = _db_path_for_case(cases_dir, case_id)
        if not db_path.exists():
            return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = get_case(logger, conn, case_id)
            if result.is_err():
                return _error_envelope(request_id, "get_case_failed", str(result.err()))
            case = result.ok()
            if case is None:
                return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")
            return _success_envelope(request_id, results=[case])
        finally:
            conn.close()

    @server.tool()
    async def ingest_records(case_id: str, domain_response: dict) -> dict:
        """Ingest entities, events, relationships, and coverage from a domain tool response."""
        request_id = generate_ulid()
        err = _validate_case_id(case_id)
        if err:
            return _error_envelope(request_id, "invalid_case_id", err)

        db_path = _db_path_for_case(cases_dir, case_id)
        if not db_path.exists():
            return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = ingest_domain_response(logger, conn, domain_response, case_id=case_id)
            if result.is_err():
                return _error_envelope(request_id, "ingest_failed", str(result.err()))
            return _success_envelope(request_id, results=[result.ok()])
        finally:
            conn.close()

    @server.tool()
    async def record_tool_call_tool(
        case_id: str,
        domain: str,
        tool_name: str,
        request_params: dict,
        response_status: str,
        response_body: dict,
        duration_ms: int | None = None,
    ) -> dict:
        """Record a tool call for reproducibility."""
        request_id = generate_ulid()
        err = _validate_case_id(case_id)
        if err:
            return _error_envelope(request_id, "invalid_case_id", err)

        db_path = _db_path_for_case(cases_dir, case_id)
        if not db_path.exists():
            return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = record_tool_call(
                logger, conn,
                case_id=case_id, request_id=request_id,
                domain=domain, tool_name=tool_name,
                request_params=request_params,
                response_status=response_status,
                response_body=response_body,
                duration_ms=duration_ms,
            )
            if result.is_err():
                return _error_envelope(request_id, "record_failed", str(result.err()))
            return _success_envelope(request_id, results=[{"tool_call_id": result.ok()}])
        finally:
            conn.close()

    @server.tool()
    async def query_entities_tool(
        case_id: str,
        entity_types: list[str] | None = None,
        kinds: list[str] | None = None,
        display_name_contains: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Query entities in a case with optional filters."""
        request_id = generate_ulid()
        err = _validate_case_id(case_id)
        if err:
            return _error_envelope(request_id, "invalid_case_id", err)

        db_path = _db_path_for_case(cases_dir, case_id)
        if not db_path.exists():
            return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = query_entities(logger, conn, entity_types, kinds, display_name_contains, limit)
            if result.is_err():
                return _error_envelope(request_id, "query_failed", str(result.err()))
            return _success_envelope(request_id, entities=result.ok())
        finally:
            conn.close()

    @server.tool()
    async def query_events_tool(
        case_id: str,
        actor_entity_id: str | None = None,
        target_entity_id: str | None = None,
        actions: list[str] | None = None,
        time_range_start: str | None = None,
        time_range_end: str | None = None,
        outcome: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Query events in a case with optional filters."""
        request_id = generate_ulid()
        err = _validate_case_id(case_id)
        if err:
            return _error_envelope(request_id, "invalid_case_id", err)

        db_path = _db_path_for_case(cases_dir, case_id)
        if not db_path.exists():
            return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = query_events(
                logger, conn, actor_entity_id, target_entity_id,
                actions, time_range_start, time_range_end, outcome, limit=limit,
            )
            if result.is_err():
                return _error_envelope(request_id, "query_failed", str(result.err()))
            return _success_envelope(request_id, events=result.ok())
        finally:
            conn.close()

    @server.tool()
    async def query_neighbors_tool(
        case_id: str,
        entity_id: str,
        relationship_types: list[str] | None = None,
        limit: int = 100,
    ) -> dict:
        """Find entities connected to a given entity via relationships."""
        request_id = generate_ulid()
        err = _validate_case_id(case_id)
        if err:
            return _error_envelope(request_id, "invalid_case_id", err)

        db_path = _db_path_for_case(cases_dir, case_id)
        if not db_path.exists():
            return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = query_neighbors(logger, conn, entity_id, relationship_types, limit)
            if result.is_err():
                return _error_envelope(request_id, "query_failed", str(result.err()))
            # Split mixed rows into separate entity and relationship lists
            raw_rows = result.ok()
            rel_keys = {"relationship_id", "relationship_type", "direction"}
            entity_list = []
            rel_list = []
            for row in raw_rows:
                rel_dict = {
                    "relationship_id": row.get("relationship_id"),
                    "relationship_type": row.get("relationship_type"),
                    "direction": row.get("direction"),
                }
                entity_dict = {k: v for k, v in row.items() if k not in rel_keys}
                entity_list.append(entity_dict)
                rel_list.append(rel_dict)
            return _success_envelope(request_id, entities=entity_list, relationships=rel_list)
        finally:
            conn.close()

    @server.tool()
    async def get_timeline_tool(
        case_id: str,
        time_range_start: str | None = None,
        time_range_end: str | None = None,
        actor_entity_id: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Get chronological event timeline for a case."""
        request_id = generate_ulid()
        err = _validate_case_id(case_id)
        if err:
            return _error_envelope(request_id, "invalid_case_id", err)

        db_path = _db_path_for_case(cases_dir, case_id)
        if not db_path.exists():
            return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = get_timeline(logger, conn, time_range_start, time_range_end, actor_entity_id, limit)
            if result.is_err():
                return _error_envelope(request_id, "query_failed", str(result.err()))
            return _success_envelope(request_id, events=result.ok())
        finally:
            conn.close()

    @server.tool()
    async def get_tool_call_history_tool(
        case_id: str,
        limit: int = 100,
    ) -> dict:
        """Get tool call history for a case, most recent first."""
        request_id = generate_ulid()
        err = _validate_case_id(case_id)
        if err:
            return _error_envelope(request_id, "invalid_case_id", err)

        db_path = _db_path_for_case(cases_dir, case_id)
        if not db_path.exists():
            return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = get_tool_call_history(logger, conn, case_id, limit)
            if result.is_err():
                return _error_envelope(request_id, "query_failed", str(result.err()))
            return _success_envelope(request_id, results=result.ok())
        finally:
            conn.close()

    @server.tool()
    async def get_report_facts_tool(case_id: str) -> dict:
        """Collect all report facts from a case in one call.

        Returns case metadata, hypotheses, claims, evidence items, timeline,
        entities, coverage reports, and tool call history.
        """
        request_id = generate_ulid()
        err = _validate_case_id(case_id)
        if err:
            return _error_envelope(request_id, "invalid_case_id", err)

        db_path = _db_path_for_case(cases_dir, case_id)
        if not db_path.exists():
            return _error_envelope(request_id, "case_not_found", f"Case '{case_id}' not found")

        db_result = open_case_db(logger, db_path)
        if db_result.is_err():
            return _error_envelope(request_id, "db_open_failed", str(db_result.err()))

        conn = db_result.ok()
        try:
            result = get_report_facts(logger, conn, case_id)
            if result.is_err():
                return _error_envelope(request_id, "query_failed", str(result.err()))
            return _success_envelope(request_id, results=[result.ok()])
        finally:
            conn.close()

    logger.info("Case MCP server configured", extra={"tool_count": len(server._tool_manager._tools)})
    return server


if __name__ == "__main__":
    from src.utils.logging import get_stderr_logger

    if len(sys.argv) < 2:
        print("Usage: python -m src.servers.case_mcp <cases_dir>", file=sys.stderr)
        sys.exit(1)

    cases_dir = Path(sys.argv[1])
    log = get_stderr_logger("case_mcp")
    server = create_case_server(cases_dir, log)
    server.run()
