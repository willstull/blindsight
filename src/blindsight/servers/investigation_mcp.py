"""Investigation orchestration MCP server.

Exposes run_investigation, describe_scenario, and follow-up case query
tools via FastMCP. Calls identity and case MCP servers as subprocesses.
See ADR-0008 for the rationale behind follow-up tools.
"""
import logging
import re
from pathlib import Path
from typing import Optional

from mcp.server import FastMCP

from blindsight.config import load_config
from blindsight.services.investigation import scenario_catalog
from blindsight.services.investigation.mcp_client import open_mcp_session, call_tool
from blindsight.services.investigation.pipeline import run_investigation


_CASE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def _discover_case_ids(cases_dir: Path) -> list[str]:
    """Return case_ids by globbing *.duckdb files in cases_dir."""
    return [p.stem for p in sorted(cases_dir.glob("*.duckdb"))
            if _CASE_ID_PATTERN.match(p.stem)]


async def _call_case_tool(
    cases_dir: Path,
    case_id: str,
    tool_name: str,
    arguments: dict,
    logger: logging.Logger,
) -> dict:
    """Validate case_id, verify DB exists on disk, spawn case MCP subprocess."""
    if not _CASE_ID_PATTERN.match(case_id):
        return {
            "status": "error",
            "error": {
                "code": "invalid_case_id",
                "message": f"Invalid case_id format: '{case_id}'.",
            },
        }
    db_path = cases_dir / f"{case_id}.duckdb"
    if not db_path.exists():
        return {
            "status": "error",
            "error": {
                "code": "case_not_found",
                "message": f"No case DB found for '{case_id}'.",
            },
        }
    async with open_mcp_session(
        "python",
        ["-m", "blindsight.servers.case_mcp", str(cases_dir)],
        logger,
    ) as session:
        return await call_tool(session, tool_name, arguments, logger)


def create_investigation_server(
    logger: logging.Logger,
    cases_dir: Path | None = None,
) -> FastMCP:
    """Create and configure the investigation orchestration MCP server."""
    if cases_dir is None:
        cases_dir = load_config().cases_dir
    cases_dir.mkdir(parents=True, exist_ok=True)

    server = FastMCP("blindsight-investigation-mcp")

    @server.tool()
    async def run_investigation_tool(
        scenario_name: str,
        investigation_question: Optional[str] = None,
        time_range_start: Optional[str] = None,
        time_range_end: Optional[str] = None,
        principal_hint: Optional[str] = None,
        max_tool_calls: int = 40,
        max_events: int = 2000,
        use_llm: bool = True,
        llm_model: Optional[str] = None,
        tlp: str = "AMBER",
        severity: str = "sev3",
    ) -> dict:
        """Run a bounded investigation against a scenario.

        Args:
            scenario_name: Scenario directory name (e.g. "credential_change_baseline") or path.
            investigation_question: Override the manifest's default question.
            time_range_start: Override time range start (RFC3339).
            time_range_end: Override time range end (RFC3339).
            principal_hint: Hint for principal search query.
            max_tool_calls: Budget for total MCP tool calls (default 40).
            max_events: Max events per search (default 2000).
            use_llm: Use LLM for gap assessment and narrative.
            llm_model: Model identifier for LLM mode.
            tlp: TLP marking for the case (default AMBER). Values: CLEAR, GREEN, AMBER, AMBER+STRICT, RED.
            severity: Severity level (default sev3). Values: sev0, sev1, sev2, sev3, sev4.

        Returns an InvestigationReport with hypothesis, scores, gaps, and steps.
        """
        scenario_path = scenario_catalog.resolve_scenario(scenario_name)
        if scenario_path is None:
            return {
                "status": "error",
                "error": {
                    "code": "scenario_not_found",
                    "message": f"Scenario '{scenario_name}' not found. Use describe_scenario to list available scenarios.",
                },
            }

        report = await run_investigation(
            scenario_path=scenario_path,
            logger=logger,
            investigation_question=investigation_question,
            time_range_start=time_range_start,
            time_range_end=time_range_end,
            principal_hint=principal_hint,
            max_tool_calls=max_tool_calls,
            max_events=max_events,
            use_llm=use_llm,
            llm_model=llm_model,
            cases_dir=str(cases_dir),
            tlp=tlp,
            severity=severity,
        )
        return report.model_dump(exclude_none=True)

    @server.tool()
    async def describe_scenario(scenario_name: Optional[str] = None) -> dict:
        """Describe a scenario, or list all available scenarios.

        Args:
            scenario_name: Scenario to describe. If omitted, lists all available scenarios.
        """
        if scenario_name is None:
            return {"scenarios": scenario_catalog.list_scenarios()}

        scenario_path = scenario_catalog.resolve_scenario(scenario_name)
        if scenario_path is None:
            return {
                "status": "error",
                "error": {
                    "code": "scenario_not_found",
                    "message": f"Scenario '{scenario_name}' not found.",
                },
                "available": scenario_catalog.list_scenarios(),
            }

        manifest = scenario_catalog.load_manifest(scenario_path)
        return {
            "scenario_name": manifest["scenario_name"],
            "description": manifest["description"],
            "investigation_question": manifest["question"],
            "time_range": {
                "start": manifest["time_range"].start,
                "end": manifest["time_range"].end,
            },
            "variant": manifest["variant"],
            "tags": manifest["tags"],
        }

    @server.tool()
    async def list_cases() -> dict:
        """List all cases discovered in the cases directory.

        Returns case metadata (id, title, status, severity, created_at)
        for each .duckdb file found. Cases persist across server restarts.
        """
        case_ids = _discover_case_ids(cases_dir)
        cases = []
        for cid in case_ids:
            result = await _call_case_tool(
                cases_dir, cid, "get_case_tool", {"case_id": cid}, logger,
            )
            if result.get("status") == "success" and result.get("results"):
                case_data = result["results"][0]
                cases.append({
                    "case_id": cid,
                    "title": case_data.get("title", ""),
                    "status": case_data.get("status", ""),
                    "severity": case_data.get("severity", ""),
                    "created_at": case_data.get("created_at", ""),
                })
            else:
                cases.append({"case_id": cid})
        return {"cases": cases}

    @server.tool()
    async def get_case_timeline(
        case_id: str,
        time_range_start: Optional[str] = None,
        time_range_end: Optional[str] = None,
        actor_entity_id: Optional[str] = None,
        limit: int = 100,
    ) -> dict:
        """Get chronological event timeline for a case.

        Args:
            case_id: Case identifier.
            time_range_start: Filter events after this time (RFC3339).
            time_range_end: Filter events before this time (RFC3339).
            actor_entity_id: Filter events by actor.
            limit: Max events to return (default 100).

        Returns the case server's timeline envelope with an 'events' key.
        """
        args = {"case_id": case_id, "limit": limit}
        if time_range_start is not None:
            args["time_range_start"] = time_range_start
        if time_range_end is not None:
            args["time_range_end"] = time_range_end
        if actor_entity_id is not None:
            args["actor_entity_id"] = actor_entity_id
        return await _call_case_tool(
            cases_dir, case_id, "get_timeline_tool", args, logger,
        )

    @server.tool()
    async def query_case_events(
        case_id: str,
        actor_entity_id: Optional[str] = None,
        target_entity_id: Optional[str] = None,
        actions: Optional[list[str]] = None,
        time_range_start: Optional[str] = None,
        time_range_end: Optional[str] = None,
        outcome: Optional[str] = None,
        limit: int = 100,
    ) -> dict:
        """Query events in a case with filters.

        Args:
            case_id: Case identifier.
            actor_entity_id: Filter by actor entity.
            target_entity_id: Filter by target entity.
            actions: Filter by action types.
            time_range_start: Filter events after this time (RFC3339).
            time_range_end: Filter events before this time (RFC3339).
            outcome: Filter by outcome (succeeded, failed, unknown).
            limit: Max events to return (default 100).

        Returns the case server's event envelope with an 'events' key.
        """
        args: dict = {"case_id": case_id, "limit": limit}
        if actor_entity_id is not None:
            args["actor_entity_id"] = actor_entity_id
        if target_entity_id is not None:
            args["target_entity_id"] = target_entity_id
        if actions is not None:
            args["actions"] = actions
        if time_range_start is not None:
            args["time_range_start"] = time_range_start
        if time_range_end is not None:
            args["time_range_end"] = time_range_end
        if outcome is not None:
            args["outcome"] = outcome
        return await _call_case_tool(
            cases_dir, case_id, "query_events_tool", args, logger,
        )

    @server.tool()
    async def query_case_entities(
        case_id: str,
        entity_types: Optional[list[str]] = None,
        kinds: Optional[list[str]] = None,
        display_name_contains: Optional[str] = None,
        limit: int = 100,
    ) -> dict:
        """Query entities in a case with filters.

        Args:
            case_id: Case identifier.
            entity_types: Filter by entity type.
            kinds: Filter by entity kind.
            display_name_contains: Substring match on display_name.
            limit: Max entities to return (default 100).

        Returns the case server's entity envelope with an 'entities' key.
        """
        args: dict = {"case_id": case_id, "limit": limit}
        if entity_types is not None:
            args["entity_types"] = entity_types
        if kinds is not None:
            args["kinds"] = kinds
        if display_name_contains is not None:
            args["display_name_contains"] = display_name_contains
        return await _call_case_tool(
            cases_dir, case_id, "query_entities_tool", args, logger,
        )

    @server.tool()
    async def query_case_neighbors(
        case_id: str,
        entity_id: str,
        relationship_types: Optional[list[str]] = None,
        limit: int = 100,
    ) -> dict:
        """Query entity neighbors via relationships in a case.

        Args:
            case_id: Case identifier.
            entity_id: Entity to find neighbors for.
            relationship_types: Filter by relationship types.
            limit: Max neighbors to return (default 100).

        Returns the case server's neighbor envelope with 'entities' and 'relationships' keys.
        """
        args: dict = {"case_id": case_id, "entity_id": entity_id, "limit": limit}
        if relationship_types is not None:
            args["relationship_types"] = relationship_types
        return await _call_case_tool(
            cases_dir, case_id, "query_neighbors_tool", args, logger,
        )

    @server.tool()
    async def get_case_tool_call_history(
        case_id: str,
        limit: int = 100,
    ) -> dict:
        """Get tool call audit history for a case.

        Args:
            case_id: Case identifier.
            limit: Max records to return (default 100).

        Returns the case server's history envelope with a 'results' key.
        """
        return await _call_case_tool(
            cases_dir, case_id, "get_tool_call_history_tool",
            {"case_id": case_id, "limit": limit}, logger,
        )

    @server.tool()
    async def generate_report(
        case_id: str,
        use_llm: bool = True,
        llm_model: Optional[str] = None,
    ) -> dict:
        """Generate a Markdown incident report from a completed investigation case.

        Collects facts from the case store, renders deterministic sections,
        and optionally generates LLM prose for human-readable sections.

        Args:
            case_id: Case identifier (must have a completed investigation).
            use_llm: Use LLM for narrative prose sections.
            llm_model: Model identifier for LLM mode.

        Returns a dict with 'report' (Markdown string) and 'facts_summary'.
        """
        from blindsight.services.investigation.reporting import (
            build_report_facts, render_report, generate_report_prose,
        )

        # Fetch facts from case store via MCP subprocess
        facts_result = await _call_case_tool(
            cases_dir, case_id, "get_report_facts_tool",
            {"case_id": case_id}, logger,
        )

        if facts_result.get("status") == "error":
            return facts_result

        results = facts_result.get("results", [])
        if not results:
            return {
                "status": "error",
                "error": {
                    "code": "no_facts",
                    "message": f"No report facts found for case '{case_id}'.",
                },
            }

        facts_payload = results[0]
        facts = build_report_facts(facts_payload)

        # Optionally generate LLM prose
        prose = None
        if use_llm:
            prose = await generate_report_prose(facts, model=llm_model)

        report_md = render_report(facts, prose)

        return {
            "status": "success",
            "report": report_md,
            "facts_summary": {
                "case_id": facts.case_id,
                "scenario_name": facts.scenario_name,
                "likelihood": facts.likelihood,
                "confidence": facts.confidence,
                "total_events": facts.total_events_evaluated,
                "claims_count": (
                    len(facts.supporting_claims)
                    + len(facts.contradicting_claims)
                    + len(facts.neutral_claims)
                ),
                "evidence_items_count": len(facts.evidence_items),
                "timeline_events_count": len(facts.timeline_events),
                "transaction_count": facts.impact.transaction_count,
                "transaction_total": facts.impact.transaction_total,
            },
        }

    logger.info("Investigation MCP server configured")
    return server


def main() -> None:
    import argparse

    from dotenv import load_dotenv
    from blindsight.utils.logging import get_stderr_logger

    parser = argparse.ArgumentParser(prog="blindsight-investigation-mcp")
    parser.add_argument("--cases-dir", type=Path, default=None)
    parser.add_argument("cases_dir_pos", nargs="?", type=Path, default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args()

    load_dotenv()
    log = get_stderr_logger("investigation_mcp")
    cases_dir = args.cases_dir or args.cases_dir_pos
    server = create_investigation_server(log, cases_dir=cases_dir)
    server.run()


if __name__ == "__main__":
    main()
