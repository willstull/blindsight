"""Application domain MCP server.

Exposes application domain tools via FastMCP. Implements the same 7-tool
domain contract as the identity server (ADR-0006). No convenience wrappers.
"""
import logging
import sys
from pathlib import Path

from mcp.server import FastMCP

from src.types.core import TimeRange
from src.types.integration import DomainIntegration
from src.utils.coverage import build_coverage_report
from src.utils.mcp_envelope import build_envelope, build_error_envelope
from src.utils.ulid import generate_ulid
from src.utils.validator import validate_limit, validate_time_range

_DOMAIN = "app"


def create_app_server(
    integration: DomainIntegration,
    logger: logging.Logger,
) -> FastMCP:
    """Create and configure the application domain MCP server."""
    server = FastMCP("blindsight-app-mcp")

    # -- Discovery tools --

    @server.tool()
    async def describe_domain() -> dict:
        """Return app domain capabilities and coverage status."""
        return await integration.describe_domain()

    @server.tool()
    async def describe_types() -> dict:
        """Return type schema for filtering/searching."""
        return await integration.describe_types()

    # -- Evidence tools --

    @server.tool()
    async def get_entity(entity_id: str) -> dict:
        """Fetch a single entity by canonical entity_id."""
        request_id = generate_ulid()
        if not entity_id or not entity_id.strip():
            return build_error_envelope(request_id, _DOMAIN, "entity_id_required", "entity_id is required")

        result = await integration.get_entity(entity_id.strip())
        envelope = build_envelope(request_id, _DOMAIN, result)

        if not result.entities:
            envelope["status"] = "error"
            envelope["error"] = {"code": "entity_not_found", "message": f"Entity '{entity_id}' not found", "severity": "error"}

        return envelope

    @server.tool()
    async def search_entities(
        query: str,
        entity_types: list[str] | None = None,
        kinds: list[str] | None = None,
        limit: int = 100,
    ) -> dict:
        """Search entities by free-text query and optional filters."""
        request_id = generate_ulid()

        lim_result = validate_limit(logger, limit, max_limit=500)
        if lim_result.is_err():
            issue = lim_result.err()
            return build_error_envelope(request_id, _DOMAIN, issue.code, issue.message)

        result = await integration.search_entities(
            query=query,
            entity_types=entity_types,
            kinds=kinds,
            limit=lim_result.ok(),
        )
        return build_envelope(request_id, _DOMAIN, result)

    @server.tool()
    async def search_events(
        time_range_start: str,
        time_range_end: str,
        actions: list[str] | None = None,
        actor_entity_ids: list[str] | None = None,
        target_entity_ids: list[str] | None = None,
        limit: int = 2000,
    ) -> dict:
        """Search normalized app events within a time range.

        Args:
            time_range_start: RFC3339 start timestamp
            time_range_end: RFC3339 end timestamp
            actions: Optional action filter (e.g. ["app.invoice.create"]). Supports prefix matching with *
            actor_entity_ids: Optional actor entity ID filter
            target_entity_ids: Optional target entity ID filter
            limit: Maximum results (default 2000)
        """
        request_id = generate_ulid()

        tr_result = validate_time_range(logger, time_range_start, time_range_end)
        if tr_result.is_err():
            issue = tr_result.err()
            return build_error_envelope(request_id, _DOMAIN, issue.code, issue.message)
        lim_result = validate_limit(logger, limit, max_limit=2000)
        if lim_result.is_err():
            issue = lim_result.err()
            return build_error_envelope(request_id, _DOMAIN, issue.code, issue.message)

        time_range = tr_result.ok()
        result = await integration.search_events(
            time_range=time_range,
            actions=actions,
            actor_entity_ids=actor_entity_ids,
            target_entity_ids=target_entity_ids,
            limit=lim_result.ok(),
        )
        return build_envelope(request_id, _DOMAIN, result)

    @server.tool()
    async def get_neighbors(
        entity_id: str,
        relationship_types: list[str] | None = None,
        time_range_start: str | None = None,
        time_range_end: str | None = None,
        depth: int = 1,
        limit: int = 2000,
    ) -> dict:
        """Traverse relationships from an entity.

        Args:
            entity_id: Starting entity ID
            relationship_types: Optional filter by relationship type
            time_range_start: Optional RFC3339 start timestamp
            time_range_end: Optional RFC3339 end timestamp
            depth: Traversal depth (1-2, default 1)
            limit: Maximum results (default 2000)
        """
        request_id = generate_ulid()
        if not entity_id or not entity_id.strip():
            return build_error_envelope(request_id, _DOMAIN, "entity_id_required", "entity_id is required")

        lim_result = validate_limit(logger, limit, max_limit=2000)
        if lim_result.is_err():
            issue = lim_result.err()
            return build_error_envelope(request_id, _DOMAIN, issue.code, issue.message)

        if bool(time_range_start) != bool(time_range_end):
            return build_error_envelope(
                request_id, _DOMAIN, "time_range_incomplete",
                "Both time_range_start and time_range_end are required when filtering by time",
            )

        time_range = None
        if time_range_start and time_range_end:
            tr_result = validate_time_range(logger, time_range_start, time_range_end)
            if tr_result.is_err():
                issue = tr_result.err()
                return build_error_envelope(request_id, _DOMAIN, issue.code, issue.message)
            time_range = tr_result.ok()

        result = await integration.get_neighbors(
            entity_id=entity_id.strip(),
            relationship_types=relationship_types,
            time_range=time_range,
            depth=min(depth, 2),
            limit=lim_result.ok(),
        )
        return build_envelope(request_id, _DOMAIN, result)

    @server.tool()
    async def describe_coverage(
        time_range_start: str,
        time_range_end: str,
        sources: list[str] | None = None,
    ) -> dict:
        """Return coverage status and gaps for the given time range.

        Args:
            time_range_start: RFC3339 start timestamp
            time_range_end: RFC3339 end timestamp
            sources: Optional filter by source names
        """
        request_id = generate_ulid()

        tr_result = validate_time_range(logger, time_range_start, time_range_end)
        if tr_result.is_err():
            issue = tr_result.err()
            return build_error_envelope(request_id, _DOMAIN, issue.code, issue.message)

        time_range = tr_result.ok()
        result = await integration.describe_coverage(
            time_range=time_range,
            sources=sources,
        )
        return build_envelope(request_id, _DOMAIN, result)

    return server


if __name__ == "__main__":
    log = logging.getLogger("app_mcp")
    log.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    log.addHandler(handler)

    if len(sys.argv) < 2:
        log.error("Usage: python -m src.servers.app_mcp <scenario_path>")
        sys.exit(1)

    scenario_path = Path(sys.argv[1])
    if not scenario_path.exists():
        log.error(f"Scenario path does not exist: {scenario_path}")
        sys.exit(1)

    from src.services.app.factory import create_app_integration
    from src.services.identity.factory import IntegrationMode

    integration = create_app_integration(
        mode=IntegrationMode.REPLAY,
        config={"scenario_path": str(scenario_path)},
        logger=log,
    )
    server = create_app_server(integration, log)
    log.info("App MCP server configured")
    print("App MCP server configured")
    server.run()
