"""Integration test: run investigation, generate report from case store.

Runs a full investigation on account_substitution_baseline (multi-domain),
then generates a report from the persisted case to verify the end-to-end
report generation pipeline.
"""
import logging
from pathlib import Path

import pytest

from functools import partial

from blindsight.services.investigation.pipeline import run_investigation as _run_investigation

# Tests run without LLM -- deterministic and no API key required
run_investigation = partial(_run_investigation, use_llm=False)
from blindsight.services.case.store import open_case_db
from blindsight.services.case.query import (
    get_report_facts, query_hypotheses, query_claims,
    query_evidence_items,
)
from blindsight.services.investigation.reporting import build_report_facts, render_report


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "replay" / "scenarios"


def _logger():
    logger = logging.getLogger("blindsight.test.report")
    logger.setLevel(logging.WARNING)
    return logger


@pytest.mark.asyncio
class TestReportGeneration:
    """End-to-end: investigate, then generate report from case store."""

    async def test_report_from_account_substitution(self, tmp_path):
        """Multi-domain investigation produces a complete report."""
        cases_dir = str(tmp_path / "cases")

        report = await run_investigation(
            FIXTURES_DIR / "account_substitution_baseline",
            _logger(),
            cases_dir=cases_dir,
        )
        assert report.case_id is not None

        # Open the case DB directly to verify persisted artifacts
        db_path = Path(cases_dir) / f"{report.case_id}.duckdb"
        assert db_path.exists()

        db_result = open_case_db(_logger(), db_path)
        assert db_result.is_ok()
        conn = db_result.ok()

        try:
            # Verify analysis artifacts were persisted
            hyp_result = query_hypotheses(_logger(), conn)
            assert hyp_result.is_ok()
            assert len(hyp_result.ok()) >= 1, "No hypotheses persisted"

            claims_result = query_claims(_logger(), conn)
            assert claims_result.is_ok()
            assert len(claims_result.ok()) >= 1, "No claims persisted"

            evidence_result = query_evidence_items(_logger(), conn)
            assert evidence_result.is_ok()
            assert len(evidence_result.ok()) >= 1, "No evidence items persisted"

            # Get report facts
            facts_result = get_report_facts(_logger(), conn, report.case_id)
            assert facts_result.is_ok()
            facts_payload = facts_result.ok()

            # Verify investigation metadata was persisted
            case = facts_payload["case"]
            assert case is not None
            metadata = case.get("investigation_metadata")
            assert metadata is not None, "Investigation metadata not persisted"
            assert metadata["scenario_name"] == "account_substitution_baseline"
            assert "investigation_question" in metadata
            assert "focal_principals" in metadata
            assert "domains_queried" in metadata

            # Build ReportFacts and render
            facts = build_report_facts(facts_payload)
            report_md = render_report(facts)

            # Verify all 9 sections present
            for section_num in range(1, 10):
                assert f"## {section_num}." in report_md, f"Section {section_num} missing"

            # Verify key content
            assert facts.case_id == report.case_id
            assert facts.scenario_name == "account_substitution_baseline"
            assert facts.likelihood in ("low", "medium", "high")
            assert facts.confidence in ("low", "medium", "high")
            assert len(facts.timeline_events) > 0, "No timeline events"
            assert len(facts.tool_call_history) > 0, "No tool call history"

            # Timeline should include both identity and app events
            domains_in_timeline = {e.get("domain") for e in facts.timeline_events}
            assert "identity" in domains_in_timeline
            assert "app" in domains_in_timeline

            # Impact should show app transaction activity
            assert facts.impact.transaction_count > 0
            assert facts.impact.transaction_total is not None
            assert facts.impact.transaction_total > 0

        finally:
            conn.close()

    async def test_report_from_credential_change(self, tmp_path):
        """Identity-only investigation produces report without app impact."""
        cases_dir = str(tmp_path / "cases")

        report = await run_investigation(
            FIXTURES_DIR / "credential_change_baseline",
            _logger(),
            cases_dir=cases_dir,
        )
        assert report.case_id is not None

        db_path = Path(cases_dir) / f"{report.case_id}.duckdb"
        db_result = open_case_db(_logger(), db_path)
        assert db_result.is_ok()
        conn = db_result.ok()

        try:
            facts_result = get_report_facts(_logger(), conn, report.case_id)
            assert facts_result.is_ok()
            facts = build_report_facts(facts_result.ok())
            report_md = render_report(facts)

            # All sections present even without app domain
            for section_num in range(1, 10):
                assert f"## {section_num}." in report_md

            # Identity-only: no app transactions
            assert facts.impact.transaction_count == 0
            assert facts.impact.transaction_total is None

            # Report still has content
            assert len(report_md) > 500, "Report suspiciously short"
        finally:
            conn.close()
