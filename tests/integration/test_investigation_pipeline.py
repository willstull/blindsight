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
from functools import partial

from src.services.investigation.pipeline import run_investigation as _run_investigation
from tests.conftest import FIXTURES_DIR

# Tests run without LLM -- deterministic and no API key required
run_investigation = partial(_run_investigation, use_llm=False)

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
        assert report.likelihood_rationale != ""
        assert report.confidence_rationale != ""

    async def test_baseline_high_confidence(self):
        """Baseline (complete coverage) should have high confidence."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_baseline",
            _logger(),
        )
        assert report.confidence == "high"
        assert report.likelihood == "high"

    async def test_degraded_lower_confidence(self):
        """Degraded scenario should produce lower confidence."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_degraded_retention_gap",
            _logger(),
        )
        assert report.confidence in ("low", "medium")
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


class TestCrossScenarioFocal:
    """Verify focal resolution and scoring across scenario families.

    These tests assert on likelihood values to catch regressions where
    multi-signal scenarios collapse to a flat 0.5 (the neutral fallback).
    """

    async def test_credential_change_focal_is_alice(self):
        """Credential change baseline: alice is primary, high likelihood."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_baseline",
            _logger(),
        )
        assert report.focal_primary == "principal_alice"
        assert "principal_alice" in report.focal_principals
        # Self-directed + single IP => legitimate self-service, high likelihood
        assert report.likelihood == "high", (
            f"Credential change baseline should have high likelihood, "
            f"got {report.likelihood}"
        )
        assert report.confidence == "high"

    async def test_account_substitution_baseline(self):
        """Account substitution: multiple focal, high likelihood, app events included."""
        report = await run_investigation(
            FIXTURES_DIR / "account_substitution_baseline",
            _logger(),
        )
        assert report.confidence == "high"
        assert len(report.focal_principals) > 1, (
            f"Expected multiple focal principals, got: {report.focal_principals}"
        )
        # Question names garcia.carlos and mreyes -- both should be focal
        assert "principal_garcia_carlos" in report.focal_principals, (
            f"garcia_carlos should be focal, got: {report.focal_principals}"
        )
        assert "principal_mreyes" in report.focal_principals, (
            f"mreyes should be focal, got: {report.focal_principals}"
        )
        # With app domain events, jef_greenfield has the most evidence activity
        # (17 app events: invoices, payments, user updates) so becomes primary focal
        assert report.focal_primary in ("principal_garcia_carlos", "principal_jef_greenfield"), (
            f"Expected garcia_carlos or jef_greenfield as primary focal, got: {report.focal_primary}"
        )
        # Account substitution has lifecycle + cross-actor: should classify and score
        assert report.likelihood == "high", (
            f"Account substitution baseline should have high likelihood, "
            f"got {report.likelihood}"
        )
        # Hypothesis should reflect the account manipulation pattern
        assert "manipulation" in report.hypothesis.lower(), (
            f"Expected account manipulation hypothesis, got: {report.hypothesis}"
        )

    async def test_superadmin_escalation_baseline(self):
        """Superadmin escalation: privilege pattern, non-trivial likelihood."""
        report = await run_investigation(
            FIXTURES_DIR / "superadmin_escalation_baseline",
            _logger(),
        )
        assert report.confidence == "high"
        assert len(report.focal_principals) > 0
        # Privilege escalation has self-grants + cross-actor: should classify and score
        assert report.likelihood == "high", (
            f"Superadmin escalation baseline should have high likelihood, "
            f"got {report.likelihood}"
        )

    async def test_focal_not_collapsed_account_substitution(self):
        """Account substitution focal should contain multiple principals."""
        report = await run_investigation(
            FIXTURES_DIR / "account_substitution_baseline",
            _logger(),
        )
        assert len(report.focal_principals) > 1, (
            f"Focal should not be collapsed to single principal: {report.focal_principals}"
        )

    async def test_password_takeover_baseline(self):
        """Password takeover: credential takeover hypothesis, non-trivial likelihood."""
        report = await run_investigation(
            FIXTURES_DIR / "password_takeover_baseline",
            _logger(),
        )
        assert report.confidence == "high"
        assert len(report.focal_principals) > 0
        # Cross-account credential reset: should classify as credential takeover
        assert report.likelihood == "high", (
            f"Password takeover baseline should have high likelihood, "
            f"got {report.likelihood}"
        )
        # Hypothesis should reference credential takeover, not account manipulation
        assert "credential takeover" in report.hypothesis.lower(), (
            f"Password takeover baseline should produce a credential takeover "
            f"hypothesis, got: {report.hypothesis}"
        )

    async def test_degraded_retention_gap_lower_confidence(self):
        """Degraded retention gap should have lower confidence."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_degraded_retention_gap",
            _logger(),
        )
        assert report.confidence in ("low", "medium")


class TestMultiDomainPipeline:
    """Tests that app domain events are incorporated when available."""

    async def test_multi_domain_increases_event_count(self):
        """Account substitution with app domain should have more events than identity alone."""
        report = await run_investigation(
            FIXTURES_DIR / "account_substitution_baseline",
            _logger(),
        )
        # Identity-only was 21 events. With app domain, should be 21 + 17 = 38.
        assert report.total_events_evaluated > 21, (
            f"Expected multi-domain event count > 21, got {report.total_events_evaluated}"
        )

    async def test_app_events_in_step_findings(self):
        """Pipeline step findings should mention app events."""
        report = await run_investigation(
            FIXTURES_DIR / "account_substitution_baseline",
            _logger(),
        )
        step_text = " ".join(
            f for s in report.steps for f in s.key_findings
        )
        assert "app event" in step_text.lower(), (
            f"Expected 'app event' in step findings, got: {step_text}"
        )

    async def test_identity_only_still_works(self):
        """Credential change (no app domain) should still work normally."""
        report = await run_investigation(
            FIXTURES_DIR / "credential_change_baseline",
            _logger(),
        )
        assert report.likelihood == "high"
        assert report.confidence == "high"
        # No app events -- only identity domain events
        assert report.total_events_evaluated > 0

    async def test_multi_domain_likelihood_high(self):
        """Account substitution baseline with app domain should still score high."""
        report = await run_investigation(
            FIXTURES_DIR / "account_substitution_baseline",
            _logger(),
        )
        assert report.likelihood == "high"
        assert report.confidence == "high"

