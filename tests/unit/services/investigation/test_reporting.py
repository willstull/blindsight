"""Tests for incident report generation service."""
import pytest

from blindsight.types.report import ReportFacts, ReportImpact, ReportProse
from blindsight.services.investigation.reporting import (
    render_report, compute_impact, build_report_facts,
)
from blindsight.types.core import GapAssessment


def _make_facts(**overrides) -> ReportFacts:
    """Build a minimal ReportFacts with sensible defaults."""
    defaults = dict(
        case_id="case-001",
        scenario_name="test_scenario",
        investigation_question="Was this malicious?",
        time_range_start="2026-03-01T00:00:00Z",
        time_range_end="2026-03-31T23:59:59Z",
        domains_queried=["identity"],
        hypothesis_statement="Credential compromise detected",
        likelihood="high",
        confidence="medium",
        likelihood_rationale="Multiple credential changes",
        confidence_rationale="Partial coverage in audit logs",
        gap_assessments=[],
        supporting_claims=[
            {"statement": "Password was changed", "confidence": 0.9, "polarity": "supports"},
        ],
        contradicting_claims=[],
        neutral_claims=[],
        evidence_items=[
            {"id": "ev-001", "domain": "identity", "summary": "Password reset event"},
        ],
        timeline_events=[
            {
                "id": "evt-001", "ts": "2026-03-15T10:00:00Z", "domain": "identity",
                "action": "auth.credential.change", "actor": {"actor_entity_id": "user-1"},
                "outcome": "succeeded",
            },
        ],
        focal_principals=["user-1"],
        focal_primary="user-1",
        entities=[{"id": "user-1", "entity_type": "principal", "display_name": "Alice"}],
        impact=ReportImpact(),
        coverage_reports=[
            {
                "id": "cov-001", "domain": "identity", "overall_status": "complete",
                "sources": [{"source_name": "audit_log", "status": "complete"}],
            },
        ],
        report_tlp="AMBER",
        tool_call_history=[
            {"tool_name": "search_events", "domain": "identity",
             "response_status": "success", "executed_at": "2026-03-15T10:05:00Z"},
        ],
        total_events_evaluated=42,
        generated_at="2026-03-15T12:00:00Z",
    )
    defaults.update(overrides)
    return ReportFacts(**defaults)


class TestComputeImpact:
    def test_empty_events(self):
        impact = compute_impact([], [])
        assert impact.transaction_count == 0
        assert impact.transaction_total is None
        assert impact.affected_principals == []
        assert impact.affected_resources == []
        assert impact.app_actions_summary == []

    def test_identity_events_excluded(self):
        events = [
            {"domain": "identity", "action": "auth.login",
             "actor": {"actor_entity_id": "user-1"}, "targets": [], "outcome": "succeeded"},
        ]
        impact = compute_impact(events, [])
        assert impact.transaction_count == 0
        assert impact.app_actions_summary == []

    def test_app_invoice_counted(self):
        events = [
            {"domain": "app", "action": "app.invoice.create",
             "actor": {"actor_entity_id": "user-1"},
             "targets": [{"target_entity_id": "resource_financial_system"}],
             "context": {"amount": 1500.00},
             "outcome": "succeeded"},
        ]
        entities = [
            {"id": "resource_financial_system", "entity_type": "resource"},
        ]
        impact = compute_impact(events, entities)
        assert impact.transaction_count == 1
        assert impact.transaction_total == 1500.00
        assert len(impact.affected_principals) == 1
        assert "resource_financial_system" in impact.affected_resources

    def test_app_payment_counted(self):
        events = [
            {"domain": "app", "action": "app.payment.create",
             "actor": {"actor_entity_id": "user-2"},
             "targets": [{"target_entity_id": "resource_payment_system"}],
             "context": {"amount": 750.50},
             "outcome": "succeeded"},
        ]
        entities = [
            {"id": "resource_payment_system", "entity_type": "resource"},
        ]
        impact = compute_impact(events, entities)
        assert impact.transaction_count == 1
        assert impact.transaction_total == 750.50

    def test_non_transaction_app_events(self):
        events = [
            {"domain": "app", "action": "app.vendor.create",
             "actor": {"actor_entity_id": "user-1"},
             "targets": [{"target_entity_id": "vendor-001"}],
             "outcome": "succeeded"},
        ]
        impact = compute_impact(events, [])
        assert impact.transaction_count == 0
        assert impact.transaction_total is None
        assert len(impact.app_actions_summary) == 1
        assert impact.app_actions_summary[0]["action"] == "app.vendor.create"

    def test_multiple_transactions_sum(self):
        events = [
            {"domain": "app", "action": "app.invoice.create",
             "actor": {"actor_entity_id": "user-1"}, "targets": [],
             "context": {"amount": 1000}, "outcome": "succeeded"},
            {"domain": "app", "action": "app.payment.create",
             "actor": {"actor_entity_id": "user-1"}, "targets": [],
             "context": {"amount": 500}, "outcome": "succeeded"},
        ]
        impact = compute_impact(events, [])
        assert impact.transaction_count == 2
        assert impact.transaction_total == 1500.0

    def test_missing_amount_still_counts(self):
        events = [
            {"domain": "app", "action": "app.invoice.create",
             "actor": {"actor_entity_id": "user-1"}, "targets": [],
             "context": {}, "outcome": "succeeded"},
        ]
        impact = compute_impact(events, [])
        assert impact.transaction_count == 1
        assert impact.transaction_total is None

    def test_entities_contribute_principals(self):
        entities = [
            {"id": "user-1", "entity_type": "principal"},
            {"id": "cred-1", "entity_type": "credential"},
        ]
        impact = compute_impact([], entities)
        assert "user-1" in impact.affected_principals
        assert "cred-1" not in impact.affected_principals


class TestBuildReportFacts:
    def test_minimal_payload(self):
        payload = {
            "case": {
                "id": "case-001",
                "investigation_metadata": {
                    "scenario_name": "test",
                    "investigation_question": "What happened?",
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                    "domains_queried": ["identity"],
                    "focal_principals": ["user-1"],
                    "focal_primary": "user-1",
                    "likelihood_rationale": "Evidence suggests compromise",
                    "confidence_rationale": "Full coverage",
                    "total_events_evaluated": 10,
                },
            },
            "hypotheses": [
                {
                    "statement": "Account was compromised",
                    "likelihood": "high",
                    "confidence": "medium",
                    "gap_assessments": [],
                },
            ],
            "claims": [
                {"statement": "Password changed", "polarity": "supports", "confidence": 0.9},
            ],
            "evidence_items": [],
            "timeline": [],
            "entities": [],
            "coverage_reports": [],
            "tool_call_history": [],
        }
        facts = build_report_facts(payload)
        assert facts.case_id == "case-001"
        assert facts.scenario_name == "test"
        assert facts.likelihood == "high"
        assert facts.confidence == "medium"
        assert len(facts.supporting_claims) == 1
        assert len(facts.contradicting_claims) == 0

    def test_empty_payload(self):
        facts = build_report_facts({})
        assert facts.case_id == "unknown"
        assert facts.hypothesis_statement == "No hypothesis available"

    def test_gap_assessments_parsed(self):
        payload = {
            "case": {"id": "c1", "investigation_metadata": {}},
            "hypotheses": [{
                "statement": "test",
                "likelihood": "high",
                "confidence": "low",
                "gap_assessments": [
                    {"gap_id": "gap-1", "relevance": "critical",
                     "could_change_conclusion": True, "reason": "Missing MFA logs"},
                ],
            }],
            "claims": [], "evidence_items": [], "timeline": [],
            "entities": [], "coverage_reports": [], "tool_call_history": [],
        }
        facts = build_report_facts(payload)
        assert len(facts.gap_assessments) == 1
        assert facts.gap_assessments[0].gap_id == "gap-1"
        assert facts.gap_assessments[0].relevance == "critical"


class TestRenderReport:
    def test_all_nine_sections_present(self):
        facts = _make_facts()
        report = render_report(facts)
        for section_num in range(1, 10):
            assert f"## {section_num}." in report, f"Section {section_num} missing"

    def test_scope_section_has_case_id(self):
        facts = _make_facts()
        report = render_report(facts)
        assert "case-001" in report

    def test_timeline_table(self):
        facts = _make_facts()
        report = render_report(facts)
        assert "| Time | Domain | Action | Actor | Target | Outcome |" in report
        assert "auth.credential.change" in report

    def test_empty_timeline(self):
        facts = _make_facts(timeline_events=[])
        report = render_report(facts)
        assert "No events recorded" in report

    def test_evidence_items_listed(self):
        facts = _make_facts()
        report = render_report(facts)
        assert "Password reset event" in report

    def test_hypothesis_assessment(self):
        facts = _make_facts()
        report = render_report(facts)
        assert "Credential compromise detected" in report
        assert "**Likelihood**: high" in report
        assert "**Confidence**: medium" in report

    def test_gap_assessment_table(self):
        facts = _make_facts(gap_assessments=[
            GapAssessment(
                gap_id="gap-1", relevance="critical",
                could_change_conclusion=True, reason="Missing MFA data",
            ),
        ])
        report = render_report(facts)
        assert "gap-1" in report
        assert "critical" in report
        assert "Missing MFA data" in report

    def test_impact_section(self):
        facts = _make_facts(impact=ReportImpact(
            affected_principals=["user-1", "user-2"],
            affected_resources=["inv-001"],
            app_actions_summary=[{"action": "app.invoice.create", "count": 3}],
            transaction_count=3,
            transaction_total=4500.00,
        ))
        report = render_report(facts)
        assert "Affected principals**: 2" in report
        assert "$4,500.00" in report

    def test_reproducibility_appendix(self):
        facts = _make_facts()
        report = render_report(facts)
        assert "Reproducibility Appendix" in report
        assert "case-001" in report
        assert "search_events" in report

    def test_report_with_prose(self):
        facts = _make_facts()
        prose = ReportProse(
            executive_summary="This is a custom executive summary.",
            key_findings_narrative="Key findings narrative here.",
            hypothesis_explanation="Hypothesis explained.",
            recommended_followup="Follow up actions.",
        )
        report = render_report(facts, prose)
        assert "This is a custom executive summary." in report
        assert "Key findings narrative here." in report
        assert "Hypothesis explained." in report
        assert "Follow up actions." in report

    def test_report_without_prose_uses_fallback(self):
        facts = _make_facts()
        report = render_report(facts, prose=None)
        # Fallback should still produce non-empty sections
        assert "test_scenario" in report
        assert "Was this malicious?" in report

    def test_deterministic_stability(self):
        """Same facts produce same report (excluding generated_at timestamp)."""
        facts = _make_facts()
        r1 = render_report(facts)
        r2 = render_report(facts)
        assert r1 == r2


class TestClaimStrength:
    def test_strong(self):
        from blindsight.services.investigation.reporting import claim_strength
        assert claim_strength(0.9) == "strong"
        assert claim_strength(0.85) == "strong"

    def test_moderate(self):
        from blindsight.services.investigation.reporting import claim_strength
        assert claim_strength(0.7) == "moderate"
        assert claim_strength(0.65) == "moderate"

    def test_weak(self):
        from blindsight.services.investigation.reporting import claim_strength
        assert claim_strength(0.5) == "weak"
        assert claim_strength(0.0) == "weak"


class TestMigrationDiscovery:
    def test_discover_migrations(self):
        from blindsight.services.case.store import _discover_migrations
        migrations = _discover_migrations()
        versions = [v for v, _ in migrations]
        assert versions == [1, 2, 3]

    def test_migration_files_exist(self):
        from blindsight.services.case.store import _MIGRATIONS_DIR
        assert (_MIGRATIONS_DIR / "001_initial.sql").exists()
        assert (_MIGRATIONS_DIR / "002_categorical_scoring.sql").exists()
        assert (_MIGRATIONS_DIR / "003_investigation_metadata.sql").exists()

    def test_investigation_metadata_column_exists(self, case_db):
        """Migration 003 adds investigation_metadata column to cases."""
        columns = case_db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'cases' AND column_name = 'investigation_metadata'"
        ).fetchall()
        assert len(columns) == 1


class TestUpdateCaseMetadata:
    def test_update_and_retrieve(self, case_db):
        from tests.conftest import get_test_logger
        from blindsight.services.case.store import update_case_metadata, get_case

        logger = get_test_logger()
        metadata = {
            "scenario_name": "test_scenario",
            "investigation_question": "What happened?",
            "focal_principals": ["user-1"],
        }
        result = update_case_metadata(logger, case_db, "case-001", metadata)
        assert result.is_ok()

        case_result = get_case(logger, case_db, "case-001")
        assert case_result.is_ok()
        case = case_result.ok()
        assert case["investigation_metadata"]["scenario_name"] == "test_scenario"
        assert case["investigation_metadata"]["focal_principals"] == ["user-1"]
