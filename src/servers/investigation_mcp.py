"""Investigation orchestration MCP server.

Exposes run_investigation and describe_scenario tools via FastMCP.
Calls identity and case MCP servers as subprocesses per investigation.
"""
import logging
import sys
from pathlib import Path
from typing import Optional

from mcp.server import FastMCP

from src.services.investigation.pipeline import run_investigation
from src.types.core import TimeRange
from src.utils.serialization import load_yaml


_SCENARIOS_DIR = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "replay" / "scenarios"


def _resolve_scenario(scenario_name: str) -> Path | None:
    """Resolve a scenario name to its directory path.

    Accepts either:
    - A bare name (e.g. "account_substitution_baseline") resolved under the scenarios dir
    - An absolute or relative path to a scenario directory
    """
    as_path = Path(scenario_name)
    if as_path.is_dir() and (as_path / "manifest.yaml").exists():
        return as_path

    candidate = _SCENARIOS_DIR / scenario_name
    if candidate.is_dir() and (candidate / "manifest.yaml").exists():
        return candidate

    return None


def _load_manifest(scenario_path: Path) -> dict:
    """Read manifest.yaml and return structured metadata."""
    manifest = load_yaml(scenario_path / "manifest.yaml")
    time_range = manifest.get("time_range", {})
    return {
        "scenario_name": manifest.get("scenario_name", scenario_path.name),
        "description": manifest.get("description", ""),
        "question": manifest.get("investigation_question", ""),
        "time_range": TimeRange(
            start=time_range.get("start", "2026-01-01T00:00:00Z"),
            end=time_range.get("end", "2026-01-31T23:59:59Z"),
        ),
        "variant": manifest.get("variant", "unknown"),
        "tags": manifest.get("tags", []),
        "domains": manifest.get("domains", []),
    }


def _list_scenarios() -> list[dict]:
    """List all available scenarios with basic metadata."""
    scenarios = []
    if not _SCENARIOS_DIR.is_dir():
        return scenarios
    for path in sorted(_SCENARIOS_DIR.iterdir()):
        if path.is_dir() and (path / "manifest.yaml").exists():
            manifest = _load_manifest(path)
            scenarios.append({
                "name": path.name,
                "description": manifest["description"],
                "variant": manifest["variant"],
            })
    return scenarios


def create_investigation_server(
    logger: logging.Logger,
) -> FastMCP:
    """Create and configure the investigation orchestration MCP server."""
    server = FastMCP("blindsight-investigation-mcp")

    @server.tool()
    async def run_investigation_tool(
        scenario_name: str,
        investigation_question: Optional[str] = None,
        time_range_start: Optional[str] = None,
        time_range_end: Optional[str] = None,
        principal_hint: Optional[str] = None,
        max_tool_calls: int = 30,
        max_events: int = 2000,
        use_llm: bool = False,
        llm_model: Optional[str] = None,
    ) -> dict:
        """Run a bounded investigation against a scenario.

        Args:
            scenario_name: Scenario directory name (e.g. "credential_change_baseline") or path.
            investigation_question: Override the manifest's default question.
            time_range_start: Override time range start (RFC3339).
            time_range_end: Override time range end (RFC3339).
            principal_hint: Hint for principal search query.
            max_tool_calls: Budget for total MCP tool calls (default 30).
            max_events: Max events per search (default 2000).
            use_llm: Use LLM for narrative text (scores always mechanical).
            llm_model: Model identifier for LLM mode.

        Returns an InvestigationReport with hypothesis, scores, gaps, and steps.
        """
        scenario_path = _resolve_scenario(scenario_name)
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
        )
        return report.model_dump(exclude_none=True)

    @server.tool()
    async def describe_scenario(scenario_name: Optional[str] = None) -> dict:
        """Describe a scenario, or list all available scenarios.

        Args:
            scenario_name: Scenario to describe. If omitted, lists all available scenarios.
        """
        if scenario_name is None:
            return {"scenarios": _list_scenarios()}

        scenario_path = _resolve_scenario(scenario_name)
        if scenario_path is None:
            return {
                "status": "error",
                "error": {
                    "code": "scenario_not_found",
                    "message": f"Scenario '{scenario_name}' not found.",
                },
                "available": _list_scenarios(),
            }

        manifest = _load_manifest(scenario_path)
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

    logger.info("Investigation MCP server configured")
    return server


if __name__ == "__main__":
    from src.utils.logging import get_stderr_logger

    log = get_stderr_logger("investigation_mcp")
    server = create_investigation_server(log)
    server.run()
