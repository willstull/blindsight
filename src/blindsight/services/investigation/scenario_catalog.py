"""Scenario catalog service.

Resolves and describes replay scenarios bundled with the package or
overridden via BLINDSIGHT_SCENARIOS_DIR. Used by the investigation
MCP server (`describe_scenario` tool) and the `blindsight` CLI.
"""
from pathlib import Path

from blindsight.config import load_config
from blindsight.types.core import TimeRange
from blindsight.utils.serialization import load_yaml


def _scenarios_dir() -> Path:
    return load_config().scenarios_dir


def resolve_scenario(scenario_name: str) -> Path | None:
    """Resolve a scenario name to its directory path.

    Accepts either a bare name (e.g. "credential_change_baseline")
    resolved under the configured scenarios dir, or an absolute or
    relative path to a scenario directory.
    """
    as_path = Path(scenario_name)
    if as_path.is_dir() and (as_path / "manifest.yaml").exists():
        return as_path

    candidate = _scenarios_dir() / scenario_name
    if candidate.is_dir() and (candidate / "manifest.yaml").exists():
        return candidate

    return None


def load_manifest(scenario_path: Path) -> dict:
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


def list_scenarios() -> list[dict]:
    """List all available scenarios with basic metadata."""
    scenarios = []
    scenarios_root = _scenarios_dir()
    if not scenarios_root.is_dir():
        return scenarios
    for path in sorted(scenarios_root.iterdir()):
        if path.is_dir() and (path / "manifest.yaml").exists():
            manifest = load_manifest(path)
            scenarios.append({
                "name": path.name,
                "description": manifest["description"],
                "variant": manifest["variant"],
            })
    return scenarios


def describe_scenario(scenario_name: str | None = None) -> dict:
    """Describe a scenario, or list all available scenarios.

    Returns the same shape used by the investigation MCP `describe_scenario`
    tool so the CLI and MCP clients render identical output.
    """
    if scenario_name is None:
        return {"scenarios": list_scenarios()}

    scenario_path = resolve_scenario(scenario_name)
    if scenario_path is None:
        return {
            "status": "error",
            "error": {
                "code": "scenario_not_found",
                "message": f"Scenario '{scenario_name}' not found.",
            },
            "available": list_scenarios(),
        }

    manifest = load_manifest(scenario_path)
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
