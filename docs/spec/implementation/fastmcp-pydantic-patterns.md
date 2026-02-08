# FastMCP and Pydantic-AI Patterns

Extracted from the NL2SQL MCP server at `~/dev/business-intelligence/bi-api`.

## Tech Stack

- **FastMCP**: MCP server framework (`from mcp.server import FastMCP`)
- **Pydantic-AI**: LLM agent framework with structured outputs
- **DuckDB**: Embedded SQL database for case store
- **result**: Result type library (`from result import Result, Ok, Err`)
- **Pydantic**: For JSON data received from outside (API requests, LLM outputs)
- **dataclasses**: For everything else (internal types, database models, response objects)

## Server Setup Pattern

```python
# servers/identity_mcp.py
from mcp.server import FastMCP
from logging import Logger

def create_logger_with_context(base_logger: Logger, service: str) -> Logger:
    """Create service-specific logger with consistent fields"""
    return base_logger.bind(
        service=service,
        transport="stdio"
    )

async def create_mcp_server(logger: Logger, config: Config) -> FastMCP:
    """
    Create and configure MCP server with all tools registered.

    This is the server factory pattern - keeps main() clean.
    """
    logger = create_logger_with_context(logger, "identity_mcp")
    logger.info("Identity plane MCP server starting")

    # Create server instance
    server = FastMCP("blindsight-identity-plane")

    # Create any shared dependencies (connection factories, config, etc.)
    scenario_path = Path(config.replay_scenarios_dir)

    # Register tools with dependencies
    register_search_events_tool(server, logger, config, scenario_path)
    register_get_entity_tool(server, logger, config, scenario_path)
    register_describe_plane_tool(server, logger, config, scenario_path)

    logger.info("Identity plane initialized", tools=["search_events", "get_entity", "describe_plane"])
    return server
```

## Tool Registration Pattern

Tools are registered as functions with a separate handler for logic.

```python
# servers/identity_mcp.py (continued)

def register_search_events_tool(
    server: FastMCP,
    logger: Logger,
    config: Config,
    scenario_path: Path
):
    """Register search_events tool with MCP server"""

    @server.tool()
    async def search_events(
        start: str,
        end: str,
        actions: list[str] | None = None,
        actor_entity_ids: list[str] | None = None,
        limit: int = 2000
    ) -> dict:
        """
        Search normalized identity events within time range.

        Args:
            start: ISO8601 timestamp (e.g. "2026-01-01T00:00:00Z")
            end: ISO8601 timestamp
            actions: Optional list of action names to filter
            actor_entity_ids: Optional list of entity IDs to filter by actor
            limit: Maximum results to return (default 2000)
        """
        result = await search_events_handler(
            server, logger, config, scenario_path,
            start, end, actions, actor_entity_ids, limit
        )
        return result.dict()  # Tool response object with .dict() method
```

Key points:
- `@server.tool()` decorator registers the function
- Docstring becomes tool description for LLM
- Type hints define JSON schema for parameters
- Return plain dict (FastMCP handles JSON serialization)
- Handler function contains actual logic (separated from registration)

## Tool Handler Pattern

Handlers orchestrate service functions and manage resources.

```python
# services/identity/search_events_handler.py
from result import Result, Ok, Err
from ulid import ULID
from logging import Logger
from pathlib import Path

from types.core import ActionEvent, CoverageReport
from types.envelope import SearchEventsResponse
from services.identity.replay_adapter import load_events
from services.identity.validator import validate_time_range
from services.identity.coverage import generate_coverage_report
from utils.time import parse_iso8601

async def search_events_handler(
    server: FastMCP,
    logger: Logger,
    config: Config,
    scenario_path: Path,
    start: str,
    end: str,
    actions: list[str] | None,
    actor_entity_ids: list[str] | None,
    limit: int
) -> SearchEventsResponse:
    """
    Handle search_events tool invocation.
    Orchestrates: validate → load → search → coverage → response.
    """
    # Generate request ID and enrich logger
    request_id = str(ULID())
    logger = logger.bind(
        request_id=request_id,
        tool="search_events"
    )
    logger.info("search_events tool invoked")

    # Parse time range
    start_dt = parse_iso8601(start)
    end_dt = parse_iso8601(end)
    time_range = TimeRange(start=start_dt, end=end_dt)

    # Stage 1: Validate
    validate_op = validate_time_range(logger, start_dt, end_dt, max_days=90)
    if validate_op.is_err():
        issue = validate_op.err()
        logger.warning("Validation failed", error_code=issue.code)
        return SearchEventsResponse(
            status="error",
            plane="identity",
            error=issue,
            request_id=request_id
        )

    # Stage 2: Load events from replay fixtures
    load_op = load_events(logger, scenario_path)
    if load_op.is_err():
        logger.error("Failed to load events")
        return SearchEventsResponse(
            status="error",
            plane="identity",
            error=PipelineError(
                code="load_failed",
                message="Failed to load event fixtures",
                severity="error"
            ),
            request_id=request_id
        )

    all_events = load_op.ok()

    # Stage 3: Filter events
    search_op = search_events_service(
        logger, all_events, time_range, actions, actor_entity_ids
    )
    if search_op.is_err():
        logger.error("Search failed")
        return SearchEventsResponse(
            status="error",
            plane="identity",
            error=PipelineError(code="search_failed", message="Search operation failed"),
            request_id=request_id
        )

    results = search_op.ok()[:limit]

    # Stage 4: Generate coverage report
    coverage_op = generate_coverage_report(logger, "identity", time_range, scenario_path)
    if coverage_op.is_err():
        logger.warning("Failed to generate coverage report")
        coverage = None
    else:
        coverage = coverage_op.ok()

    logger.info("search_events completed", status="success", result_count=len(results))
    return SearchEventsResponse(
        status="success",
        plane="identity",
        coverage_report=coverage,
        items=results,
        request_id=request_id
    )
```

Handler responsibilities:
- Generate request ID and enrich logger with context
- Orchestrate service function calls (validate → load → process → respond)
- Handle Result types from services (check `.is_err()`, extract `.ok()` or `.err()`)
- Return response object (not dict)
- Log at stage boundaries

## Response Objects Pattern

Response objects use dataclasses with a `.dict()` method for JSON serialization.

```python
# types/envelope.py
from dataclasses import dataclass, asdict
from typing import Optional, List

from types.core import ActionEvent, CoverageReport
from types.errors import PipelineError

@dataclass
class SearchEventsResponse:
    """Response from search_events tool"""
    status: str  # "success", "partial", "error"
    plane: str
    request_id: str
    coverage_report: Optional[CoverageReport] = None
    items: Optional[List[ActionEvent]] = None
    error: Optional[PipelineError] = None
    limitations: Optional[List[str]] = None
    next_page_token: Optional[str] = None

    def dict(self) -> dict:
        """Convert to dict for MCP response, omitting None values"""
        result = {}
        for key, value in asdict(self).items():
            if value is not None:
                result[key] = value
        return result
```

Key points:
- Use `@dataclass` for internal response objects
- Include `.dict()` method that omits None values
- Return from handler, convert to dict in tool registration

**When to use Pydantic vs dataclass:**
- **Pydantic**: JSON data from outside (MCP tool inputs, LLM structured outputs)
- **dataclasses**: Everything internal (entities, events, responses, pipeline results)

## Service Functions with Result Types

Services return `Result[T, Exception]` instead of raising exceptions.

```python
# services/identity/replay_adapter.py
from result import Result, Ok, Err
from pathlib import Path
from logging import Logger
from typing import List
import json

from types.core import ActionEvent

def load_events(
    logger: Logger,
    scenario_path: Path
) -> Result[List[ActionEvent], Exception]:
    """Load events from NDJSON fixture."""
    try:
        events_file = scenario_path / "planes" / "identity" / "events.ndjson"

        if not events_file.exists():
            logger.warning(f"Events file not found: {events_file}")
            return Ok([])  # Empty list is success, not error

        events = []
        with events_file.open() as f:
            for line in f:
                event_dict = json.loads(line)
                events.append(ActionEvent(**event_dict))

        logger.info(f"Loaded {len(events)} events")
        return Ok(events)

    except Exception as ex:
        logger.exception("Failed to load events", extra={"scenario_path": str(scenario_path)})
        return Err(ex)
```

At call site:
```python
load_op = load_events(logger, scenario_path)
if load_op.is_err():
    # Handle error
    return error_response()

events = load_op.ok()
# Use events
```

## Pydantic-AI Agent Pattern (for SQL generation)

Use Pydantic-AI when you need LLM to generate structured output. Pydantic models define the output schema.

```python
# services/case/sql_agent.py
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from dataclasses import dataclass, field
from logging import Logger
from result import Result, Ok, Err

from types.core import Entity

class SQLQueryOutput(BaseModel):
    """Structured output from Pydantic-AI agent - use Pydantic for LLM outputs"""
    sql: str = Field(description="Single SELECT statement - ONLY SQL, no markdown")
    assumptions: List[str] = Field(description="Assumptions made", default_factory=list)
    tables_used: List[str] = Field(description="Tables referenced in query")

@dataclass
class SQLGenerationDeps:
    """Dependencies for SQL generation agent - use dataclass for internal deps"""
    entities: List[Entity]
    schema_description: str

async def generate_case_query(
    logger: Logger,
    question: str,
    entities: List[Entity],
    schema_description: str,
    model: str = "claude-sonnet-4"
) -> Result[SQLQueryOutput, Exception]:
    """Generate SQL query to answer question about case data using Pydantic-AI."""
    try:
        logger.info("Generating SQL query", question_length=len(question))

        # Create dependencies
        deps = SQLGenerationDeps(
            entities=entities,
            schema_description=schema_description
        )

        # Create agent with structured output
        agent = Agent(
            model=f'anthropic:{model}',
            output_type=SQLQueryOutput,
            system_prompt=_build_system_prompt(),
        )

        # Build user prompt
        user_prompt = f"""Schema:
{schema_description}

Available entities: {len(entities)} entities loaded

Question: {question}

Generate SQL using ONLY the schema above."""

        # Run agent
        result = await agent.run(user_prompt, deps=deps)

        sql_output = result.data
        logger.info("SQL generated", sql_length=len(sql_output.sql), tables=sql_output.tables_used)

        return Ok(sql_output)

    except Exception as ex:
        logger.exception("SQL generation failed", extra={"question": question})
        return Err(ex)

def _build_system_prompt() -> str:
    return """You are a SQL query generator for investigation case data.

Rules:
- Generate ONLY SELECT statements
- Use only tables/columns from provided schema
- Return single SQL statement (no multiple queries)
- Omit markdown formatting
"""
```

Key points:
- **Pydantic `BaseModel`** for LLM structured output (data coming from outside)
- **dataclass** for agent dependencies (internal data)
- Agent returns `.data` attribute with typed output
- Wrap in Result type for consistency

**Rule of thumb:**
- Data from outside (LLM, API, JSON) → Pydantic
- Data inside your code (entities, events, dependencies) → dataclass

## DuckDB Query Pattern

For case store queries with DuckDB.

```python
# services/case/query.py
import duckdb
from result import Result, Ok, Err
from logging import Logger
from typing import List, Tuple
from pathlib import Path

from types.core import Entity, ActionEvent

def query_events_by_actor(
    logger: Logger,
    db_path: Path,
    actor_entity_id: str,
    limit: int = 100
) -> Result[List[ActionEvent], Exception]:
    """Query events where entity was the actor."""
    try:
        conn = duckdb.connect(str(db_path), read_only=True)

        query = """
            SELECT * FROM events
            WHERE json_extract_string(actor, '$.actor_entity_id') = ?
            ORDER BY ts DESC
            LIMIT ?
        """

        result = conn.execute(query, [actor_entity_id, limit]).fetchall()

        events = [ActionEvent(**dict(zip(
            [desc[0] for desc in conn.description],
            row
        ))) for row in result]

        conn.close()

        logger.info(f"Found {len(events)} events for actor {actor_entity_id}")
        return Ok(events)

    except Exception as ex:
        logger.exception("Query failed", extra={"actor_id": actor_entity_id})
        return Err(ex)
```

Key points for Blindsight case store:
- Read-only connections when querying (`read_only=True`)
- Use parameterized queries (`?` placeholders)
- JSON extraction for nested fields (`json_extract_string`)
- Close connections explicitly (no connection pooling needed for local DB)
- Return Result types
- Log query results for debugging

## Logger Enrichment Pattern

Pass logger explicitly and enrich at boundaries.

```python
# At entrypoint (handler)
request_id = str(ULID())
logger = logger.bind(
    request_id=request_id,
    tool="search_events",
    catalog="identity"
)

# Pass enriched logger to services
result = some_service(logger, other_params)

# In service functions
def some_service(logger: Logger, ...):
    logger.info("Starting work", additional_field="value")
    # Logger carries request_id, tool, catalog automatically
```

## Error Handling Pattern

Structured errors with codes and severity.

```python
# types/errors.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class PipelineError:
    """Structured error with retry metadata"""
    code: str  # e.g. "time_range_required", "load_failed"
    message: str
    severity: str  # "error", "warning", "fatal"
    context: Optional[dict] = None
    retryable: bool = False

@dataclass
class ValidationIssue:
    """Validation-specific error"""
    code: str
    message: str
    severity: str
    field: Optional[str] = None
```

## Key Differences from Generic Patterns

1. **FastMCP, not generic MCP**: Use `from mcp.server import FastMCP` and specific registration patterns
2. **Pydantic vs dataclass split**:
   - Pydantic: JSON from outside (LLM outputs, API requests)
   - dataclass: Internal types (entities, events, responses, dependencies)
3. **Handler + service separation**: Handlers orchestrate, services do work
4. **Result types everywhere**: No exceptions as control flow
5. **Logger enrichment at boundaries**: Pass explicit logger with context
6. **Response objects with .dict()**: Clean JSON serialization
7. **DuckDB for case store**: Simple embedded SQL, no connection pooling needed

## What NOT to Import from NL2SQL

- RLS enforcement (not needed for local case DB)
- SQL validation with pglast (not needed unless validating user SQL)
- Catalog loading from YAML (different schema format)
- Schema rendering for LLM (different use case)
- Row caps and timeouts (less critical for local DB)

## What IS Relevant

- FastMCP server setup pattern
- Tool registration with handlers
- Pydantic-AI agent pattern for structured output
- Result types throughout
- Logger enrichment
- Response objects with .dict()
- DuckDB query patterns (basic SELECT, JSON extraction)
- ULID for request correlation
