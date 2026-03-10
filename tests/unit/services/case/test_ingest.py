"""Tests for case store ingest operations."""
import json

import pytest

from tests.conftest import get_test_logger
from src.services.case.ingest import (
    ingest_entities, ingest_events, ingest_relationships,
    ingest_coverage_report, ingest_domain_response, record_tool_call,
    ingest_evidence_items, ingest_claims, ingest_assumptions, ingest_hypotheses,
)
from src.services.case.json_helpers import from_json
from src.types.core import (
    Entity, ActionEvent, Relationship, CoverageReport,
    Actor, Target, Ref, TimeRange, SourceStatus,
    EvidenceItem, Claim, Assumption, Hypothesis,
)


def _make_entity(id="ent-001", entity_type="principal", kind="user", display_name="Alice"):
    return Entity(
        id=id, tlp="GREEN", entity_type=entity_type, kind=kind,
        display_name=display_name,
        refs=[Ref(ref_type="email", system="okta", value="alice@example.com")],
        attributes={"department": "engineering"},
        first_seen="2026-01-01T00:00:00Z",
        last_seen="2026-01-02T00:00:00Z",
        confidence=0.95,
    )


def _make_event(id="evt-001", actor_id="ent-001", target_id="ent-002"):
    return ActionEvent(
        id=id, tlp="GREEN", domain="identity",
        ts="2026-01-15T10:00:00Z", action="credential.reset",
        actor=Actor(actor_entity_id=actor_id),
        targets=[Target(target_entity_id=target_id, role="subject")],
        outcome="succeeded",
        raw_refs=[Ref(ref_type="log_id", system="okta", value="log-123")],
        context={"ip": "10.0.0.1"},
    )


def _make_relationship(id="rel-001", from_id="ent-001", to_id="ent-002"):
    return Relationship(
        id=id, tlp="GREEN", domain="identity",
        relationship_type="has_credential",
        from_entity_id=from_id, to_entity_id=to_id,
        first_seen="2026-01-01T00:00:00Z",
    )


def _make_coverage():
    return CoverageReport(
        id="cov-001", tlp="GREEN", domain="identity",
        time_range=TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z"),
        overall_status="complete",
        sources=[SourceStatus(source_name="okta", status="complete")],
        notes="Full coverage",
    )


class TestIngestEntities:
    def test_ingest_single_entity(self, case_db):
        logger = get_test_logger()
        entity = _make_entity()
        result = ingest_entities(logger, case_db, [entity])
        assert result.is_ok()
        assert result.ok() == 1

        row = case_db.execute("SELECT * FROM entities WHERE id = 'ent-001'").fetchone()
        assert row is not None
        cols = [d[0] for d in case_db.description]
        data = dict(zip(cols, row))
        assert data["display_name"] == "Alice"
        refs = from_json(data["refs"])
        assert refs[0]["value"] == "alice@example.com"

    def test_ingest_entity_upsert(self, case_db):
        logger = get_test_logger()
        e1 = _make_entity(display_name="Alice v1")
        e2 = _make_entity(display_name="Alice v2")
        ingest_entities(logger, case_db, [e1])
        ingest_entities(logger, case_db, [e2])

        row = case_db.execute("SELECT display_name FROM entities WHERE id = 'ent-001'").fetchone()
        assert row[0] == "Alice v2"

    def test_ingest_entity_with_no_refs(self, case_db):
        logger = get_test_logger()
        entity = Entity(id="ent-bare", tlp="GREEN", entity_type="resource", kind="app",
                        display_name="App1", refs=[])
        result = ingest_entities(logger, case_db, [entity])
        assert result.is_ok()
        row = case_db.execute("SELECT refs FROM entities WHERE id = 'ent-bare'").fetchone()
        assert from_json(row[0]) == []


class TestIngestEvents:
    def test_ingest_single_event(self, case_db):
        logger = get_test_logger()
        ingest_entities(logger, case_db, [_make_entity("ent-001"), _make_entity("ent-002", display_name="Bob")])
        result = ingest_events(logger, case_db, [_make_event()])
        assert result.is_ok()
        assert result.ok() == 1

        row = case_db.execute("SELECT * FROM events WHERE id = 'evt-001'").fetchone()
        cols = [d[0] for d in case_db.description]
        data = dict(zip(cols, row))
        actor = from_json(data["actor"])
        assert actor["actor_entity_id"] == "ent-001"
        targets = from_json(data["targets"])
        assert targets[0]["target_entity_id"] == "ent-002"

    def test_ingest_event_with_empty_targets(self, case_db):
        logger = get_test_logger()
        event = ActionEvent(
            id="evt-no-targets", tlp="GREEN", domain="identity",
            ts="2026-01-15T10:00:00Z", action="session.start",
            actor=Actor(actor_entity_id="ent-001"), targets=[], outcome="succeeded",
        )
        result = ingest_events(logger, case_db, [event])
        assert result.is_ok()
        row = case_db.execute("SELECT targets FROM events WHERE id = 'evt-no-targets'").fetchone()
        assert from_json(row[0]) == []


class TestIngestRelationships:
    def test_ingest_single_relationship(self, case_db):
        logger = get_test_logger()
        ingest_entities(logger, case_db, [_make_entity("ent-001"), _make_entity("ent-002", display_name="Bob")])
        result = ingest_relationships(logger, case_db, [_make_relationship()])
        assert result.is_ok()
        assert result.ok() == 1

    def test_ingest_relationship_without_entities(self, case_db):
        """Relationships can be ingested without referenced entities (no FK constraints)."""
        logger = get_test_logger()
        result = ingest_relationships(logger, case_db, [_make_relationship()])
        assert result.is_ok()
        assert result.ok() == 1


class TestIngestCoverageReport:
    def test_ingest_coverage(self, case_db):
        logger = get_test_logger()
        result = ingest_coverage_report(logger, case_db, _make_coverage())
        assert result.is_ok()
        assert result.ok() == "cov-001"

        row = case_db.execute("SELECT * FROM coverage_reports WHERE id = 'cov-001'").fetchone()
        cols = [d[0] for d in case_db.description]
        data = dict(zip(cols, row))
        assert data["overall_status"] == "complete"
        sources = from_json(data["sources"])
        assert sources[0]["source_name"] == "okta"

    def test_ingest_coverage_upsert(self, case_db):
        logger = get_test_logger()
        cov1 = _make_coverage()
        ingest_coverage_report(logger, case_db, cov1)

        cov2 = CoverageReport(
            id="cov-001", tlp="GREEN", domain="identity",
            time_range=TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z"),
            overall_status="partial",
            sources=[SourceStatus(source_name="okta", status="partial")],
            notes="Updated coverage",
        )
        result = ingest_coverage_report(logger, case_db, cov2)
        assert result.is_ok()

        row = case_db.execute("SELECT overall_status, notes FROM coverage_reports WHERE id = 'cov-001'").fetchone()
        assert row[0] == "partial"
        assert row[1] == "Updated coverage"


class TestIngestDomainResponse:
    def test_ingest_full_response(self, case_db):
        logger = get_test_logger()
        response = {
            "entities": [
                _make_entity("ent-001").model_dump(exclude_none=True),
                _make_entity("ent-002", display_name="Bob").model_dump(exclude_none=True),
            ],
            "events": [_make_event().model_dump(exclude_none=True)],
            "relationships": [_make_relationship().model_dump(exclude_none=True)],
            "coverage_report": _make_coverage().model_dump(exclude_none=True),
        }
        result = ingest_domain_response(logger, case_db, response)
        assert result.is_ok()
        counts = result.ok()
        assert counts["entities"] == 2
        assert counts["events"] == 1
        assert counts["relationships"] == 1
        assert counts["coverage_reports"] == 1

    def test_ingest_empty_response(self, case_db):
        logger = get_test_logger()
        result = ingest_domain_response(logger, case_db, {})
        assert result.is_ok()
        counts = result.ok()
        assert counts == {"entities": 0, "events": 0, "relationships": 0, "coverage_reports": 0}

    def test_ingest_entities_only(self, case_db):
        logger = get_test_logger()
        response = {"entities": [_make_entity().model_dump(exclude_none=True)]}
        result = ingest_domain_response(logger, case_db, response)
        assert result.is_ok()
        assert result.ok()["entities"] == 1
        assert result.ok()["events"] == 0


class TestRecordToolCall:
    def test_record_and_query(self, case_db):
        logger = get_test_logger()
        result = record_tool_call(
            logger, case_db,
            case_id="case-001", request_id="req-001",
            domain="identity", tool_name="search_events",
            request_params={"time_range_start": "2026-01-01T00:00:00Z"},
            response_status="success",
            response_body={"items": []},
            duration_ms=42,
        )
        assert result.is_ok()
        tool_call_id = result.ok()

        row = case_db.execute("SELECT * FROM tool_calls WHERE id = ?", [tool_call_id]).fetchone()
        cols = [d[0] for d in case_db.description]
        data = dict(zip(cols, row))
        assert data["tool_name"] == "search_events"
        assert data["duration_ms"] == 42
        params = from_json(data["request_params"])
        assert params["time_range_start"] == "2026-01-01T00:00:00Z"


# -- Analytic object tests --

def _make_evidence_item(id="evi-001"):
    return EvidenceItem(
        id=id, tlp="GREEN", domain="identity",
        summary="Credential reset observed from known IP",
        raw_refs=[Ref(ref_type="log_id", system="okta", value="log-456")],
        collected_at="2026-01-15T10:00:00Z",
        related_entity_ids=["ent-001"],
        related_event_ids=["evt-001"],
        hash="sha256:abc123",
    )


def _make_claim(id="clm-001"):
    return Claim(
        id=id, tlp="GREEN",
        statement="All credential changes were self-directed",
        polarity="supports", confidence=0.9,
        backed_by_evidence_ids=["evi-001"],
    )


def _make_assumption(id="asm-001"):
    return Assumption(
        id=id, tlp="GREEN",
        statement="Okta logs are complete for the time range",
        strength="solid",
        rationale="Coverage report shows complete status for Okta source",
        impacts=["confidence_limit depends on log completeness"],
    )


def _make_hypothesis(id="hyp-001"):
    return Hypothesis(
        id=id, tlp="AMBER", iq_id="IQ-001",
        statement="Credential changes are legitimate self-service activity",
        likelihood_score=0.85, confidence_limit=0.95,
        supporting_claim_ids=["clm-001"],
        gaps=["cov-001"],
        next_evidence_requests=[
            {"domain": "identity", "tool": "search_events",
             "params": {"actions": ["auth.*"]}, "priority": "low"},
        ],
        status="open",
    )


class TestIngestEvidenceItems:
    def test_ingest_single(self, case_db):
        logger = get_test_logger()
        result = ingest_evidence_items(logger, case_db, [_make_evidence_item()])
        assert result.is_ok()
        assert result.ok() == 1

        row = case_db.execute("SELECT * FROM evidence_items WHERE id = 'evi-001'").fetchone()
        assert row is not None
        cols = [d[0] for d in case_db.description]
        data = dict(zip(cols, row))
        assert data["summary"] == "Credential reset observed from known IP"
        assert data["hash"] == "sha256:abc123"
        refs = from_json(data["raw_refs"])
        assert refs[0]["value"] == "log-456"
        assert from_json(data["related_entity_ids"]) == ["ent-001"]

    def test_upsert(self, case_db):
        logger = get_test_logger()
        ingest_evidence_items(logger, case_db, [_make_evidence_item()])
        updated = _make_evidence_item()
        updated.summary = "Updated summary"
        ingest_evidence_items(logger, case_db, [updated])

        row = case_db.execute("SELECT summary FROM evidence_items WHERE id = 'evi-001'").fetchone()
        assert row[0] == "Updated summary"


class TestIngestClaims:
    def test_ingest_single(self, case_db):
        logger = get_test_logger()
        result = ingest_claims(logger, case_db, [_make_claim()])
        assert result.is_ok()
        assert result.ok() == 1

        row = case_db.execute("SELECT * FROM claims WHERE id = 'clm-001'").fetchone()
        cols = [d[0] for d in case_db.description]
        data = dict(zip(cols, row))
        assert data["polarity"] == "supports"
        assert data["confidence"] == 0.9
        assert from_json(data["backed_by_evidence_ids"]) == ["evi-001"]

    def test_upsert(self, case_db):
        logger = get_test_logger()
        ingest_claims(logger, case_db, [_make_claim()])
        updated = _make_claim()
        updated.confidence = 0.75
        ingest_claims(logger, case_db, [updated])

        row = case_db.execute("SELECT confidence FROM claims WHERE id = 'clm-001'").fetchone()
        assert row[0] == 0.75

    def test_claim_with_all_optional_fields(self, case_db):
        logger = get_test_logger()
        claim = Claim(
            id="clm-full", tlp="AMBER",
            statement="Derived claim with all fields",
            polarity="contradicts", confidence=0.6,
            backed_by_evidence_ids=["evi-001", "evi-002"],
            subject_entity_ids=["ent-001"],
            time_range=TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z"),
            derived_from_claim_ids=["clm-001"],
            assumption_ids=["asm-001"],
        )
        result = ingest_claims(logger, case_db, [claim])
        assert result.is_ok()

        row = case_db.execute("SELECT * FROM claims WHERE id = 'clm-full'").fetchone()
        cols = [d[0] for d in case_db.description]
        data = dict(zip(cols, row))
        assert from_json(data["subject_entity_ids"]) == ["ent-001"]
        assert from_json(data["derived_from_claim_ids"]) == ["clm-001"]
        assert from_json(data["assumption_ids"]) == ["asm-001"]
        assert data["time_range_start"] is not None
        assert data["time_range_end"] is not None


class TestIngestAssumptions:
    def test_ingest_single(self, case_db):
        logger = get_test_logger()
        result = ingest_assumptions(logger, case_db, [_make_assumption()])
        assert result.is_ok()
        assert result.ok() == 1

        row = case_db.execute("SELECT * FROM assumptions WHERE id = 'asm-001'").fetchone()
        cols = [d[0] for d in case_db.description]
        data = dict(zip(cols, row))
        assert data["strength"] == "solid"
        assert from_json(data["impacts"]) == ["confidence_limit depends on log completeness"]

    def test_upsert(self, case_db):
        logger = get_test_logger()
        ingest_assumptions(logger, case_db, [_make_assumption()])
        updated = _make_assumption()
        updated.strength = "caveated"
        ingest_assumptions(logger, case_db, [updated])

        row = case_db.execute("SELECT strength FROM assumptions WHERE id = 'asm-001'").fetchone()
        assert row[0] == "caveated"


class TestIngestHypotheses:
    def test_ingest_single(self, case_db):
        logger = get_test_logger()
        result = ingest_hypotheses(logger, case_db, [_make_hypothesis()])
        assert result.is_ok()
        assert result.ok() == 1

        row = case_db.execute("SELECT * FROM hypotheses WHERE id = 'hyp-001'").fetchone()
        cols = [d[0] for d in case_db.description]
        data = dict(zip(cols, row))
        assert data["likelihood_score"] == 0.85
        # confidence_limit maps to confidence_cap column
        assert data["confidence_cap"] == 0.95
        assert data["iq_id"] == "IQ-001"
        assert data["status"] == "open"
        assert from_json(data["supporting_claim_ids"]) == ["clm-001"]
        assert from_json(data["gaps"]) == ["cov-001"]

    def test_upsert(self, case_db):
        logger = get_test_logger()
        ingest_hypotheses(logger, case_db, [_make_hypothesis()])
        updated = _make_hypothesis()
        updated.likelihood_score = 0.5
        updated.confidence_limit = 0.6
        ingest_hypotheses(logger, case_db, [updated])

        row = case_db.execute(
            "SELECT likelihood_score, confidence_cap FROM hypotheses WHERE id = 'hyp-001'"
        ).fetchone()
        assert row[0] == 0.5
        assert row[1] == 0.6

    def test_next_evidence_requests_json_roundtrip(self, case_db):
        logger = get_test_logger()
        requests = [
            {"domain": "identity", "tool": "search_events",
             "params": {"actions": ["credential.*"], "time_range_start": "2026-01-01T00:00:00Z"},
             "priority": "high"},
            {"domain": "network", "tool": "get_flows",
             "params": {"src_ip": "10.0.0.1"}, "priority": "medium"},
        ]
        hyp = _make_hypothesis()
        hyp.next_evidence_requests = requests
        ingest_hypotheses(logger, case_db, [hyp])

        row = case_db.execute(
            "SELECT next_evidence_requests FROM hypotheses WHERE id = 'hyp-001'"
        ).fetchone()
        stored = from_json(row[0])
        assert len(stored) == 2
        assert stored[0]["domain"] == "identity"
        assert stored[0]["params"]["actions"] == ["credential.*"]
        assert stored[1]["tool"] == "get_flows"
        assert stored[1]["priority"] == "medium"
