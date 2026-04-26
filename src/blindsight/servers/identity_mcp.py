"""Identity domain MCP server.

Exposes identity domain tools via FastMCP. Each tool handler validates inputs,
calls the integration, and wraps results into a ResponseEnvelope.
"""
import logging
import sys
from pathlib import Path
from typing import Optional

from mcp.server import FastMCP

from blindsight import MCP_CONTRACT_VERSION
from blindsight.types.core import TimeRange
from blindsight.types.integration import DomainIntegration
from blindsight.utils.coverage import build_coverage_report
from blindsight.utils.mcp_envelope import build_envelope, build_error_envelope
from blindsight.utils.ulid import generate_ulid
from blindsight.utils.validator import validate_limit, validate_time_range

_DOMAIN = "identity"


def create_identity_server(
    integration: DomainIntegration,
    logger: logging.Logger,
) -> FastMCP:
    """Create and configure the identity domain MCP server."""
    server = FastMCP("blindsight-identity-mcp")

    # -- Discovery tools (return dict directly) --

    @server.tool()
    async def describe_domain() -> dict:
        """Return identity domain capabilities and coverage status."""
        result = await integration.describe_domain()
        result["contract_version"] = MCP_CONTRACT_VERSION
        return result

    @server.tool()
    async def describe_types() -> dict:
        """Return type schema for filtering/searching (entity types, relationship types, context fields)."""
        return await integration.describe_types()

    # -- Evidence tools (return ResponseEnvelope) --

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
        """Search normalized identity events within a time range.

        Args:
            time_range_start: RFC3339 start timestamp (e.g. "2026-01-01T00:00:00Z")
            time_range_end: RFC3339 end timestamp
            actions: Optional action filter (e.g. ["credential.reset"]). Supports prefix matching with * (e.g. "credential.*")
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

        # Reject partial time range -- both or neither
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

    # -- Convenience tools (thin wrappers) --

    @server.tool()
    async def resolve_principal(
        identifiers: list[dict],
        limit: int = 50,
    ) -> dict:
        """Resolve principal candidates by email/username/external refs.

        Args:
            identifiers: List of ref objects with ref_type, system, value
            limit: Maximum results (default 50)
        """
        request_id = generate_ulid()
        # Extract search terms from identifier values
        search_terms = [ident.get("value", "") for ident in identifiers if ident.get("value")]
        query = " ".join(search_terms) if search_terms else ""
        result = await integration.search_entities(
            query=query,
            entity_types=["principal"],
            limit=min(limit, 50),
        )
        return build_envelope(request_id, _DOMAIN, result)

    @server.tool()
    async def get_principal(principal_entity_id: str) -> dict:
        """Fetch a principal by principal_entity_id."""
        request_id = generate_ulid()
        if not principal_entity_id or not principal_entity_id.strip():
            return build_error_envelope(request_id, _DOMAIN, "entity_id_required", "principal_entity_id is required")

        result = await integration.get_entity(principal_entity_id.strip())
        envelope = build_envelope(request_id, _DOMAIN, result)

        if not result.entities:
            envelope["status"] = "error"
            envelope["error"] = {"code": "entity_not_found", "message": f"Principal '{principal_entity_id}' not found", "severity": "error"}

        return envelope

    @server.tool()
    async def list_credential_changes(
        principal_entity_id: str,
        time_range_start: str,
        time_range_end: str,
    ) -> dict:
        """List credential/factor changes for a principal.

        Args:
            principal_entity_id: The principal entity ID
            time_range_start: RFC3339 start timestamp
            time_range_end: RFC3339 end timestamp
        """
        request_id = generate_ulid()

        tr_result = validate_time_range(logger, time_range_start, time_range_end)
        if tr_result.is_err():
            issue = tr_result.err()
            return build_error_envelope(request_id, _DOMAIN, issue.code, issue.message)

        time_range = tr_result.ok()
        result = await integration.search_events(
            time_range=time_range,
            actions=["credential.*"],
            actor_entity_ids=[principal_entity_id],
        )
        return build_envelope(request_id, _DOMAIN, result)

    logger.info("Identity MCP server configured", extra={"tool_count": len(server._tool_manager._tools)})
    return server


def main() -> None:
    import argparse

    from blindsight.utils.logging import get_stderr_logger
    from blindsight.services.identity.factory import (
        create_identity_integration,
        IntegrationMode,
    )

    parser = argparse.ArgumentParser(prog="blindsight-identity-mcp")
    parser.add_argument("--scenario-path", type=Path, default=None)
    parser.add_argument("scenario_path_pos", nargs="?", type=Path, default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    scenario_path = args.scenario_path or args.scenario_path_pos
    if scenario_path is None:
        print("Usage: blindsight-identity-mcp --scenario-path <path>", file=sys.stderr)
        sys.exit(1)
    if not scenario_path.exists():
        print(f"Scenario path not found: {scenario_path}", file=sys.stderr)
        sys.exit(1)

    log = get_stderr_logger("identity_mcp")
    integration = create_identity_integration(
        mode=IntegrationMode.REPLAY,
        config={"scenario_path": str(scenario_path)},
        logger=log,
    )
    server = create_identity_server(integration, log)
    server.run()


if __name__ == "__main__":
    main()
