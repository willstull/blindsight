# Code Organization

This document defines the structure and conventions for Blindsight implementation.

## Project Scope

Two MCP servers:

1. **Identity MCP Server**: Evidence domain providing normalized identity telemetry (replay-backed, optionally live-backed)
2. **Case MCP Server**: Case record store providing persistence, correlation queries, and export/replay

This is not "just an MCP server." The practicum demonstrates:
- Tool contract + schema discipline
- Replay dataset format
- Deterministic evaluation harness with degraded variants
- Case record persistence (DuckDB)
- Normalization + normalized IDs + correlation pivots
- Coverage/missing-data reporting
- Regression tests (golden outputs)

## Directory Structure

```
src/
  types/
    core.py            # Entity, ActionEvent, Relationship, CoverageReport,
                       # EvidenceItem, Claim, Hypothesis, Case
    integration.py     # IntegrationResponse, DomainIntegration interface
    envelope.py        # ResponseEnvelope, Status enum
    result.py          # Result[T, E] union type
    errors.py          # PipelineError, ValidationIssue

  services/
    identity/
      replay_integration.py  # ReplayIdentityIntegration implementation
      live_integration.py    # LiveIdentityIntegration stub (optional)
      validator.py           # Request validation functions
      coverage.py            # Coverage report generation
      normalize.py           # Normalization functions (raw → normalized)

    case/
      store.py         # DuckDB case store operations
      ingest.py        # Ingest normalized records into case
      query.py         # Correlation queries across entities/events
      export.py        # Export case data (for replay/archival)

  servers/
    identity_mcp.py    # Identity domain MCP server
    case_mcp.py        # Case MCP server

  utils/
    logging.py         # Logger factory
    ulid.py            # ULID generation
    pagination.py      # Cursor encoding/decoding
    time.py            # Time normalization helpers

tests/
  fixtures/
    replay/
      scenarios/
        baseline/              # Complete coverage scenario
          manifest.yaml
          domains/identity/
            entities.ndjson
            events.ndjson
            relationships.ndjson
            coverage.yaml
          expected_output.json

        degraded_missing_source/   # Missing source variant
        degraded_retention_gap/    # Retention gap variant

  unit/
    services/
      identity/
        test_replay_integration.py
        test_validator.py
        test_coverage.py
        test_normalize.py
      case/
        test_store.py
        test_ingest.py
        test_query.py

  integration/
    test_replay_scenarios.py
    test_case_correlation.py
```

## Safeloop Principles

Following the coding style defined in the Safeloop article:

1. **Pass dependencies explicitly**: No ambient imports of connections, loggers, config
2. **Return Result types**: Functions return `Result[T, Exception]` instead of raising
3. **Separate data from functionality**: Types in `types/`, logic in `services/`
4. **Entrypoints manage resources**: Servers handle connections, transactions, logging context
5. **Services are unaware of intent**: Individual units of work, composable at entrypoint
6. **Avoid importing services in services**: Import graph forms a DAG

## Type Definitions

Types define data structure only. No methods except serialization helpers (e.g. `to_dict()`). All types in `types/` use Pydantic BaseModel for automatic nested parsing (`model_validate()`) and serialization (`model_dump(exclude_none=True)`).

```python
# types/core.py
from typing import Optional
from pydantic import BaseModel, Field

class Entity(BaseModel):
    id: str
    tlp: str
    entity_type: str
    kind: str
    display_name: str
    refs: list[Ref] = Field(default_factory=list)
    attributes: Optional[dict] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    confidence: Optional[float] = None

class ActionEvent(BaseModel):
    id: str
    tlp: str
    domain: str
    ts: str  # RFC3339
    action: str
    actor: Actor
    targets: list[Target] = Field(default_factory=list)
    outcome: str = "unknown"
    raw_refs: list[Ref] = Field(default_factory=list)
    context: Optional[dict] = None
    related_entity_ids: Optional[list[str]] = None
    ingested_at: Optional[str] = None

class CoverageReport(BaseModel):
    id: str
    tlp: str
    domain: str
    time_range: TimeRange
    overall_status: str
    sources: list[SourceStatus] = Field(default_factory=list)
    missing_fields: Optional[list[str]] = None
    data_latency_seconds: Optional[float] = None
    quality_flags: Optional[list[str]] = None
    notes: Optional[str] = None
```

## Service Functions: Identity Domain

Identity services provide evidence from telemetry sources.

```python
# services/identity/replay_integration.py
from result import Result, Ok, Err
from pathlib import Path
from logging import Logger
from typing import List

from types.core import Entity, ActionEvent
from types.envelope import ResponseEnvelope
from types.errors import PipelineError

def load_entities(
    logger: Logger,
    scenario_path: Path
) -> Result[List[Entity], Exception]:
    """Load entities from NDJSON fixture."""
    try:
        entities_file = scenario_path / "domains" / "identity" / "entities.ndjson"

        if not entities_file.exists():
            logger.warning(f"Entities file not found: {entities_file}")
            return Ok([])

        entities = []
        with entities_file.open() as f:
            for line in f:
                entity_dict = json.loads(line)
                entities.append(Entity(**entity_dict))

        logger.info(f"Loaded {len(entities)} entities")
        return Ok(entities)

    except Exception as ex:
        logger.exception("Failed to load entities", extra={"scenario_path": str(scenario_path)})
        return Err(ex)


def search_events(
    logger: Logger,
    events: List[ActionEvent],
    time_range: 'TimeRange',
    actions: Optional[List[str]] = None,
    actor_entity_ids: Optional[List[str]] = None
) -> Result[List[ActionEvent], Exception]:
    """Filter events by time range and optional filters."""
    try:
        filtered = [
            e for e in events
            if time_range.start <= e.ts <= time_range.end
        ]

        if actions:
            filtered = [e for e in filtered if e.action in actions]

        if actor_entity_ids:
            filtered = [e for e in filtered if e.actor.actor_entity_id in actor_entity_ids]

        logger.info(f"Search returned {len(filtered)} events")
        return Ok(filtered)

    except Exception as ex:
        logger.exception("Search failed")
        return Err(ex)
```

## Service Functions: Case MCP Server

Case services provide persistence and correlation.

```python
# services/case/store.py
import duckdb
from result import Result, Ok, Err
from logging import Logger
from pathlib import Path
from typing import List

from types.core import Entity, ActionEvent, Relationship

def create_case_db(
    logger: Logger,
    db_path: Path
) -> Result[duckdb.DuckDBPyConnection, Exception]:
    """Create or open case database."""
    try:
        conn = duckdb.connect(str(db_path))

        # Create tables
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                id VARCHAR PRIMARY KEY,
                tlp VARCHAR,
                entity_type VARCHAR,
                kind VARCHAR,
                display_name VARCHAR,
                refs JSON,
                attributes JSON,
                first_seen TIMESTAMP,
                last_seen TIMESTAMP,
                confidence DOUBLE
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id VARCHAR PRIMARY KEY,
                tlp VARCHAR,
                domain VARCHAR,
                ts TIMESTAMP,
                action VARCHAR,
                actor JSON,
                targets JSON,
                outcome VARCHAR,
                raw_refs JSON,
                context JSON,
                related_entity_ids JSON,
                ingested_at TIMESTAMP
            )
        """)

        logger.info(f"Case database ready: {db_path}")
        return Ok(conn)

    except Exception as ex:
        logger.exception("Failed to create case database", extra={"db_path": str(db_path)})
        return Err(ex)


def insert_entities(
    logger: Logger,
    conn: duckdb.DuckDBPyConnection,
    entities: List[Entity]
) -> Result[int, Exception]:
    """Insert entities into case store."""
    try:
        count = 0
        for entity in entities:
            conn.execute("""
                INSERT OR REPLACE INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entity.id,
                entity.tlp,
                entity.entity_type,
                entity.kind,
                entity.display_name,
                json.dumps([r.__dict__ for r in entity.refs]) if entity.refs else None,
                json.dumps(entity.attributes) if entity.attributes else None,
                entity.first_seen,
                entity.last_seen,
                entity.confidence
            ))
            count += 1

        logger.info(f"Inserted {count} entities")
        return Ok(count)

    except Exception as ex:
        logger.exception("Failed to insert entities", extra={"count": len(entities)})
        return Err(ex)
```

```python
# services/case/query.py
import duckdb
from result import Result, Ok, Err
from logging import Logger
from typing import List, Tuple

from types.core import Entity, ActionEvent

def get_entity_neighbors(
    logger: Logger,
    conn: duckdb.DuckDBPyConnection,
    entity_id: str,
    relationship_types: Optional[List[str]] = None
) -> Result[List[Tuple[Entity, str]], Exception]:
    """Get entities related to this entity via relationships."""
    try:
        # Correlation query example
        query = """
            SELECT e.*, r.relationship_type
            FROM entities e
            JOIN relationships r ON (
                r.to_entity_id = e.id AND r.from_entity_id = ?
                OR r.from_entity_id = e.id AND r.to_entity_id = ?
            )
        """
        params = [entity_id, entity_id]

        if relationship_types:
            query += " WHERE r.relationship_type IN (" + ",".join(["?"] * len(relationship_types)) + ")"
            params.extend(relationship_types)

        result = conn.execute(query, params).fetchall()

        neighbors = [
            (Entity(**dict(row[:-1])), row[-1])  # entity, relationship_type
            for row in result
        ]

        logger.info(f"Found {len(neighbors)} neighbors for entity {entity_id}")
        return Ok(neighbors)

    except Exception as ex:
        logger.exception("Failed to get neighbors", extra={"entity_id": entity_id})
        return Err(ex)


def get_events_by_actor(
    logger: Logger,
    conn: duckdb.DuckDBPyConnection,
    actor_entity_id: str,
    time_range: Optional['TimeRange'] = None
) -> Result[List[ActionEvent], Exception]:
    """Get all events where entity was the actor."""
    try:
        query = """
            SELECT * FROM events
            WHERE json_extract_string(actor, '$.actor_entity_id') = ?
        """
        params = [actor_entity_id]

        if time_range:
            query += " AND ts BETWEEN ? AND ?"
            params.extend([time_range.start, time_range.end])

        query += " ORDER BY ts DESC"

        result = conn.execute(query, params).fetchall()
        events = [ActionEvent(**dict(row)) for row in result]

        logger.info(f"Found {len(events)} events for actor {actor_entity_id}")
        return Ok(events)

    except Exception as ex:
        logger.exception("Failed to get events by actor", extra={"actor_id": actor_entity_id})
        return Err(ex)
```

## Entrypoints: MCP Servers

Servers manage resources and compose service functions.

```python
# servers/identity_mcp.py
from fastmcp import FastMCP
from logging import Logger
from pathlib import Path

from services.identity.replay_integration import load_entities, search_events
from services.identity.coverage import generate_coverage_report
from services.identity.validator import validate_time_range
from utils.logging import get_logger
from utils.ulid import generate_ulid

mcp = FastMCP("blindsight-identity-mcp")

@mcp.tool()
def search_events_tool(
    start: str,
    end: str,
    actions: list[str] | None = None,
    actor_entity_ids: list[str] | None = None,
    limit: int = 2000
) -> dict:
    """Search normalized identity events within time range."""

    # Setup resources at entrypoint
    logger = get_logger("identity_domain")
    request_id = generate_ulid()
    logger = logger.bind(request_id=request_id)  # Enrich logger

    scenario_path = Path("tests/fixtures/replay/scenarios/baseline")

    # Parse time range
    time_range = TimeRange(
        start=datetime.fromisoformat(start),
        end=datetime.fromisoformat(end)
    )

    # Validate
    validate_op = validate_time_range(logger, time_range.start, time_range.end)
    if validate_op.is_err():
        issue = validate_op.err()
        return {
            "status": "error",
            "domain": "identity",
            "error": {
                "code": issue.code,
                "message": issue.message,
                "severity": issue.severity
            },
            "request_id": request_id
        }

    # Load events
    load_op = load_events(logger, scenario_path)
    if load_op.is_err():
        logger.error("Failed to load events")
        return {
            "status": "error",
            "domain": "identity",
            "error": {
                "code": "load_failed",
                "message": "Failed to load event fixtures"
            },
            "request_id": request_id
        }

    all_events = load_op.ok()

    # Search
    search_op = search_events(logger, all_events, time_range, actions, actor_entity_ids)
    if search_op.is_err():
        logger.error("Search failed")
        return {
            "status": "error",
            "domain": "identity",
            "error": {
                "code": "search_failed",
                "message": "Search operation failed"
            },
            "request_id": request_id
        }

    results = search_op.ok()[:limit]

    # Generate coverage
    coverage_op = generate_coverage_report(logger, "identity", time_range, scenario_path)
    if coverage_op.is_err():
        logger.warning("Failed to generate coverage report")
        coverage = None
    else:
        coverage = coverage_op.ok()

    return {
        "status": "success",
        "domain": "identity",
        "coverage_report": coverage.__dict__ if coverage else None,
        "items": [event.__dict__ for event in results],
        "request_id": request_id
    }


if __name__ == "__main__":
    mcp.run()
```

```python
# servers/case_mcp.py
from fastmcp import FastMCP
from pathlib import Path

from services.case.store import create_case_db, insert_entities
from services.case.query import get_entity_neighbors, get_events_by_actor
from utils.logging import get_logger
from utils.ulid import generate_ulid

mcp = FastMCP("blindsight-case-mcp")

@mcp.tool()
def ingest_entities_tool(case_id: str, entities: list[dict]) -> dict:
    """Ingest entities into case store."""

    logger = get_logger("case_mcp")
    request_id = generate_ulid()
    logger = logger.bind(request_id=request_id, case_id=case_id)

    db_path = Path(f"cases/{case_id}.duckdb")
    db_path.parent.mkdir(exist_ok=True)

    # Create/open database
    conn_op = create_case_db(logger, db_path)
    if conn_op.is_err():
        return {
            "status": "error",
            "error": {"code": "db_failed", "message": "Failed to open case database"},
            "request_id": request_id
        }

    conn = conn_op.ok()

    try:
        # Convert dicts to Entity objects
        entity_objects = [Entity(**e) for e in entities]

        # Insert
        insert_op = insert_entities(logger, conn, entity_objects)
        if insert_op.is_err():
            return {
                "status": "error",
                "error": {"code": "ingest_failed", "message": "Failed to ingest entities"},
                "request_id": request_id
            }

        count = insert_op.ok()

        return {
            "status": "success",
            "count": count,
            "request_id": request_id
        }

    finally:
        conn.close()


@mcp.tool()
def get_neighbors_tool(case_id: str, entity_id: str) -> dict:
    """Get related entities via relationships (correlation query)."""

    logger = get_logger("case_mcp")
    request_id = generate_ulid()
    logger = logger.bind(request_id=request_id, case_id=case_id)

    db_path = Path(f"cases/{case_id}.duckdb")

    if not db_path.exists():
        return {
            "status": "error",
            "error": {"code": "case_not_found", "message": "Case database not found"},
            "request_id": request_id
        }

    conn_op = create_case_db(logger, db_path)
    if conn_op.is_err():
        return {
            "status": "error",
            "error": {"code": "db_failed", "message": "Failed to open case database"},
            "request_id": request_id
        }

    conn = conn_op.ok()

    try:
        neighbors_op = get_entity_neighbors(logger, conn, entity_id)
        if neighbors_op.is_err():
            return {
                "status": "error",
                "error": {"code": "query_failed", "message": "Correlation query failed"},
                "request_id": request_id
            }

        neighbors = neighbors_op.ok()

        return {
            "status": "success",
            "items": [
                {"entity": e.__dict__, "relationship_type": rel_type}
                for e, rel_type in neighbors
            ],
            "request_id": request_id
        }

    finally:
        conn.close()


if __name__ == "__main__":
    mcp.run()
```

## Testing

```python
# tests/integration/test_case_correlation.py
import pytest
from pathlib import Path
import duckdb

from services.case.store import create_case_db, insert_entities, insert_relationships
from services.case.query import get_entity_neighbors
from utils.logging import get_logger

def test_correlation_query():
    """Test that we can correlate entities via relationships in case store."""

    logger = get_logger("test")
    db_path = Path("test_case.duckdb")

    # Setup
    conn_op = create_case_db(logger, db_path)
    assert conn_op.is_ok()
    conn = conn_op.ok()

    # Insert test entities
    user = Entity(id="user-1", tlp="GREEN", entity_type="principal", kind="user", display_name="alice", refs=[])
    session = Entity(id="session-1", tlp="GREEN", entity_type="session", kind="oauth_session", display_name="session-abc", refs=[])

    insert_entities(logger, conn, [user, session])

    # Insert relationship
    rel = Relationship(
        id="rel-1",
        tlp="GREEN",
        domain="identity",
        relationship_type="authenticated_as",
        from_entity_id="session-1",
        to_entity_id="user-1"
    )
    insert_relationships(logger, conn, [rel])

    # Query neighbors
    neighbors_op = get_entity_neighbors(logger, conn, "user-1")
    assert neighbors_op.is_ok()

    neighbors = neighbors_op.ok()
    assert len(neighbors) == 1
    assert neighbors[0][0].id == "session-1"
    assert neighbors[0][1] == "authenticated_as"

    conn.close()
    db_path.unlink()
```

## Import Rules

```
servers/ (entrypoints)
    ↓
services/
    ↓
types/
    ↓
utils/ (import-only)
```

Services should not import other services. Compose at entrypoint (server).

## Key Differences from Generic MCP Patterns

This is not generic MCP advice. This is Blindsight-specific:

1. **Two MCP servers**: Identity domain (evidence) + Case (correlation/persistence)
2. **Result types throughout**: No exceptions as control flow
3. **Safeloop organization**: entrypoints → services → types
4. **Pass logger explicitly**: Enriched at entrypoint, passed to services
5. **DuckDB for case store**: Correlation queries prove multi-domain capability
6. **Replay fixtures for evaluation**: Deterministic testing with degraded variants
