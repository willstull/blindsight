"""Integration tests: run expected_tool_output.json against each scenario.

Parameterized over all 4 scenarios. Loads manifest + expected_tool_output.json,
creates ReplayIdentityIntegration, runs each tool call, compares structural
results (counts, IDs, status, coverage).
"""
import json
from pathlib import Path

import pytest

from src.services.identity.coverage import determine_response_status
from src.services.identity.replay_integration import ReplayIdentityIntegration
from src.types.core import TimeRange
from tests.conftest import ALL_SCENARIO_NAMES, get_test_logger, scenario_path_for


@pytest.fixture(params=ALL_SCENARIO_NAMES)
def scenario(request):
    name = request.param
    path = scenario_path_for(name)
    eto_path = path / "expected_tool_output.json"
    with eto_path.open() as f:
        expected = json.load(f)

    logger = get_test_logger()
    integration = ReplayIdentityIntegration(scenario_path=path, logger=logger)
    return integration, expected


class TestReplayScenarios:
    async def test_tool_calls(self, scenario):
        integration, expected = scenario

        for tc in expected["tool_calls"]:
            tool = tc["tool"]
            args = tc["args"]
            exp = tc["expected"]

            result = await self._call_tool(integration, tool, args)

            # Check status
            if "status" in exp:
                actual_status = determine_response_status(
                    result.coverage.overall_status
                ) if result.coverage else "error"
                assert actual_status == exp["status"], (
                    f"[{tool}] expected status={exp['status']}, got {actual_status}"
                )

            # Check event count
            if "event_count" in exp:
                assert len(result.events) == exp["event_count"], (
                    f"[{tool}] expected {exp['event_count']} events, got {len(result.events)}"
                )

            # Check event IDs
            if "event_ids" in exp:
                actual_ids = sorted([e.id for e in result.events])
                assert actual_ids == sorted(exp["event_ids"]), (
                    f"[{tool}] expected event_ids={exp['event_ids']}, got {actual_ids}"
                )

            # Check entity count
            if "entity_count" in exp:
                assert len(result.entities) == exp["entity_count"], (
                    f"[{tool}] expected {exp['entity_count']} entities, got {len(result.entities)}"
                )

            # Check entity IDs
            if "entity_ids" in exp:
                actual_ids = sorted([e.id for e in result.entities])
                assert actual_ids == sorted(exp["entity_ids"]), (
                    f"[{tool}] expected entity_ids={exp['entity_ids']}, got {actual_ids}"
                )

            # Check relationship count
            if "relationship_count" in exp:
                assert len(result.relationships) == exp["relationship_count"], (
                    f"[{tool}] expected {exp['relationship_count']} relationships, got {len(result.relationships)}"
                )

            # Check coverage overall status
            if "coverage_overall_status" in exp:
                assert result.coverage is not None, f"[{tool}] coverage_report is None"
                assert result.coverage.overall_status == exp["coverage_overall_status"], (
                    f"[{tool}] expected coverage={exp['coverage_overall_status']}, got {result.coverage.overall_status}"
                )

            # Check source count
            if "source_count" in exp:
                assert result.coverage is not None
                assert len(result.coverage.sources) == exp["source_count"], (
                    f"[{tool}] expected {exp['source_count']} sources, got {len(result.coverage.sources)}"
                )

    async def _call_tool(self, integration, tool, args):
        """Dispatch tool call to integration method."""
        if tool == "search_events":
            time_range = TimeRange(
                start=args["time_range_start"],
                end=args["time_range_end"],
            )
            return await integration.search_events(
                time_range=time_range,
                actions=args.get("actions"),
                actor_entity_ids=args.get("actor_entity_ids"),
                target_entity_ids=args.get("target_entity_ids"),
            )
        elif tool == "get_entity":
            return await integration.get_entity(args["entity_id"])
        elif tool == "get_neighbors":
            return await integration.get_neighbors(
                entity_id=args["entity_id"],
                relationship_types=args.get("relationship_types"),
            )
        elif tool == "describe_coverage":
            time_range = TimeRange(
                start=args["time_range_start"],
                end=args["time_range_end"],
            )
            return await integration.describe_coverage(time_range=time_range)
        else:
            pytest.fail(f"Unknown tool: {tool}")
