"""Tests for case store ingest operations."""
import json

import pytest

from tests.conftest import get_test_logger
from src.services.case.ingest import (
    ingest_entities, ingest_events, ingest_relationships,
    ingest_coverage_report, ingest_domain_response, record_tool_call,
)
from src.services.case.json_helpers import from_json
from src.types.core import (
    Entity, ActionEvent, Relationship, CoverageReport,
    Actor, Target, Ref, TimeRange, SourceStatus,
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
