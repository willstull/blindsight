"""Integration tests for the investigation pipeline.

Each test launches real identity + case MCP subprocesses against replay
data. Tests are deterministic but slower (~3s each due to subprocess startup).
"""
import json
import logging
import os
import tempfile

import pytest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from src.services.investigation.mcp_client import open_mcp_session, call_tool
from src.services.investigation.pipeline import run_investigation
from tests.conftest import FIXTURES_DIR

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _logger():
    logger = logging.getLogger("test_pipeline")
    logger.setLevel(logging.WARNING)
    return logger


class TestInvestigationPipeline:
    async def test_baseline_produces_report(self):
        """Baseline scenario runs to completion with expected structure."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_baseline",
            _logger(),
        )
        assert report.scenario_name == "credential_change_baseline"
        assert report.case_id is not None
        assert report.tool_calls_used > 0
        assert report.total_events_evaluated > 0
        assert len(report.steps) > 0
        assert report.hypothesis != ""
        assert report.likelihood_assessment != ""
        assert report.confidence_assessment != ""

    async def test_baseline_high_confidence(self):
        """Baseline (complete coverage) should have high confidence limit."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_baseline",
            _logger(),
        )
        assert report.confidence_limit == 0.95
        assert report.likelihood_score > 0.5

    async def test_degraded_lower_confidence(self):
        """Degraded scenario should produce lower confidence limit."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_degraded_retention_gap",
            _logger(),
        )
        assert report.confidence_limit < 0.95
        assert report.total_events_evaluated > 0

    async def test_steps_include_expected_stages(self):
        """Pipeline should produce steps for all major stages."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_baseline",
            _logger(),
        )
        stage_names = [s.stage for s in report.steps]
        assert "Create case" in stage_names
        assert "Check coverage" in stage_names
        assert "Discover principals" in stage_names
        assert "Search for evidence" in stage_names
        assert "Score" in stage_names

    async def test_tool_call_budget_respected(self):
        """Pipeline should not exceed the tool call budget."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_baseline",
            _logger(),
            max_tool_calls=5,
        )
        assert report.tool_calls_used <= 5

    async def test_question_override(self):
        """Explicit question should override manifest default."""
        custom_q = "Was this a test investigation?"
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_baseline",
            _logger(),
            investigation_question=custom_q,
        )
        assert report.investigation_question == custom_q

    async def test_nonexistent_scenario_fails(self):
        """Pipeline should fail cleanly for a missing scenario path."""
        with pytest.raises(Exception):
            await run_investigation(
                FIXTURES_DIR / "does_not_exist",
                _logger(),
            )

    async def test_tool_calls_recorded_in_case(self):
        """Pipeline should record tool call audit history in the case store.

        Runs the pipeline with a known cases_dir, then opens a fresh case
        server against the same directory and queries get_tool_call_history_tool
        to verify audit rows were actually written.
        """
        logger = _logger()
        cases_dir = tempfile.mkdtemp(prefix="blindsight_test_audit_")
        scenario_path = FIXTURES_DIR / "credential_change_baseline"

        report = await run_investigation(
            scenario_path, logger, cases_dir=cases_dir,
        )
        assert report.case_id is not None

        # Open a fresh case server against the same cases_dir and query history
        async with open_mcp_session(
            "python",
            [f"{_PROJECT_ROOT}/src/servers/case_mcp.py", cases_dir],
            logger,
        ) as case_session:
            history = await call_tool(case_session, "get_tool_call_history_tool", {
                "case_id": report.case_id,
                "limit": 100,
            }, logger)

            results = history.get("results", [])
            recorded_tools = [r["tool_name"] for r in results]

            # Verify key tools were recorded
            assert "create_case_tool" in recorded_tools, (
                f"create_case_tool missing from audit history: {recorded_tools}"
            )
            assert "describe_coverage" in recorded_tools, (
                f"describe_coverage missing from audit history: {recorded_tools}"
            )
            assert "search_events" in recorded_tools, (
                f"search_events missing from audit history: {recorded_tools}"
            )
            assert "search_entities" in recorded_tools, (
                f"search_entities missing from audit history: {recorded_tools}"
            )

            # Should have a substantial number of recorded calls
            assert len(results) >= 8, (
                f"Expected at least 8 recorded tool calls, got {len(results)}: {recorded_tools}"
            )
