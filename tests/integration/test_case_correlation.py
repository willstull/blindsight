"""End-to-end tests for case store correlation queries.

Tests the full workflow: create case -> ingest identity domain data -> query correlations.
Uses the baseline replay scenario fixture data.
"""
import pytest

from tests.conftest import get_test_logger
from blindsight.services.case.store import open_case_db, create_case
from blindsight.services.case.ingest import ingest_domain_response, record_tool_call
from blindsight.services.case.query import (
    query_entities, query_events, query_neighbors, get_timeline, get_tool_call_history,
)
from blindsight.types.core import (
    Entity, ActionEvent, Relationship, CoverageReport,
    Actor, Target, Ref, TimeRange, SourceStatus,
)


def _baseline_domain_response():
    """Simulate a domain tool response with identity data for Alice."""
    return {
        "entities": [
            {
                "id": "principal_alice", "tlp": "GREEN",
                "entity_type": "principal", "kind": "user",
                "display_name": "Alice Johnson",
                "refs": [{"ref_type": "email", "system": "okta", "value": "alice@example.com"}],
                "attributes": {"department": "engineering"},
            },
            {
                "id": "cred_alice_password", "tlp": "GREEN",
                "entity_type": "credential", "kind": "password",
                "display_name": "Alice Password",
                "refs": [],
            },
            {
                "id": "session_alice_web", "tlp": "GREEN",
                "entity_type": "session", "kind": "web_session",
                "display_name": "Alice Web Session",
                "refs": [{"ref_type": "session_id", "system": "okta", "value": "sess-abc123"}],
            },
            {
                "id": "cred_alice_mfa", "tlp": "GREEN",
                "entity_type": "credential", "kind": "mfa_factor",
                "display_name": "Alice MFA (TOTP)",
                "refs": [],
            },
        ],
        "events": [
            {
                "id": "evt-cred-reset", "tlp": "GREEN", "domain": "identity",
                "ts": "2026-01-15T10:00:00Z", "action": "credential.reset",
                "actor": {"actor_entity_id": "principal_alice"},
                "targets": [{"target_entity_id": "cred_alice_password", "role": "subject"}],
                "outcome": "succeeded",
                "raw_refs": [{"ref_type": "log_id", "system": "okta", "value": "log-001"}],
            },
            {
                "id": "evt-mfa-enroll", "tlp": "GREEN", "domain": "identity",
                "ts": "2026-01-15T10:05:00Z", "action": "credential.enroll",
                "actor": {"actor_entity_id": "principal_alice"},
                "targets": [{"target_entity_id": "cred_alice_mfa", "role": "subject"}],
                "outcome": "succeeded",
                "raw_refs": [{"ref_type": "log_id", "system": "okta", "value": "log-002"}],
            },
            {
                "id": "evt-session-start", "tlp": "GREEN", "domain": "identity",
                "ts": "2026-01-15T10:10:00Z", "action": "session.start",
                "actor": {"actor_entity_id": "principal_alice"},
                "targets": [{"target_entity_id": "session_alice_web", "role": "subject"}],
                "outcome": "succeeded",
                "raw_refs": [],
            },
        ],
        "relationships": [
            {
                "id": "rel-alice-pw", "tlp": "GREEN", "domain": "identity",
                "relationship_type": "has_credential",
                "from_entity_id": "principal_alice",
                "to_entity_id": "cred_alice_password",
            },
            {
                "id": "rel-alice-mfa", "tlp": "GREEN", "domain": "identity",
                "relationship_type": "has_credential",
                "from_entity_id": "principal_alice",
                "to_entity_id": "cred_alice_mfa",
            },
            {
                "id": "rel-alice-session", "tlp": "GREEN", "domain": "identity",
                "relationship_type": "has_session",
                "from_entity_id": "principal_alice",
                "to_entity_id": "session_alice_web",
            },
        ],
        "coverage_report": {
            "id": "cov-baseline", "tlp": "GREEN", "domain": "identity",
            "time_range": {"start": "2026-01-15T00:00:00Z", "end": "2026-01-15T23:59:59Z"},
            "overall_status": "complete",
            "sources": [{"source_name": "okta", "status": "complete"}],
        },
    }


@pytest.fixture
def case_with_data(tmp_path):
    """Create a case, ingest baseline data, return (conn, case_id)."""
    logger = get_test_logger()
    db_path = tmp_path / "case-e2e.duckdb"
    db_result = open_case_db(logger, db_path)
    assert db_result.is_ok()
    conn = db_result.ok()

    case_result = create_case(logger, conn, "case-e2e", "Credential Change Investigation")
    assert case_result.is_ok()

    ingest_result = ingest_domain_response(logger, conn, _baseline_domain_response())
    assert ingest_result.is_ok()

    yield conn
    conn.close()


class TestCaseCorrelation:
    def test_neighbor_pivot_from_principal(self, case_with_data):
        """From principal_alice, find all connected entities (credentials + sessions)."""
        logger = get_test_logger()
        result = query_neighbors(logger, case_with_data, entity_id="principal_alice")
        assert result.is_ok()
        neighbors = result.ok()
        assert len(neighbors) == 3
        neighbor_ids = {n["id"] for n in neighbors}
        assert neighbor_ids == {"cred_alice_password", "cred_alice_mfa", "session_alice_web"}

    def test_credential_only_neighbors(self, case_with_data):
        """Filter neighbors to only credential relationships."""
        logger = get_test_logger()
        result = query_neighbors(
            logger, case_with_data,
            entity_id="principal_alice",
            relationship_types=["has_credential"],
        )
        assert result.is_ok()
        neighbors = result.ok()
        assert len(neighbors) == 2
        neighbor_ids = {n["id"] for n in neighbors}
        assert neighbor_ids == {"cred_alice_password", "cred_alice_mfa"}

    def test_timeline_shows_investigation_sequence(self, case_with_data):
        """Timeline should show events in chronological order."""
        logger = get_test_logger()
        result = get_timeline(logger, case_with_data)
        assert result.is_ok()
        events = result.ok()
        assert len(events) == 3
        actions = [e["action"] for e in events]
        assert actions == ["credential.reset", "credential.enroll", "session.start"]

    def test_events_targeting_credential(self, case_with_data):
        """Find all events that targeted the password credential."""
        logger = get_test_logger()
        result = query_events(
            logger, case_with_data,
            target_entity_id="cred_alice_password",
        )
        assert result.is_ok()
        events = result.ok()
        assert len(events) == 1
        assert events[0]["action"] == "credential.reset"

    def test_full_investigation_workflow(self, case_with_data):
        """Simulate a multi-step investigation: find principal -> pivot to credentials -> check events."""
        logger = get_test_logger()

        # Step 1: Find the principal
        result = query_entities(logger, case_with_data, entity_types=["principal"])
        assert result.is_ok()
        principals = result.ok()
        assert len(principals) == 1
        alice = principals[0]
        assert alice["display_name"] == "Alice Johnson"

        # Step 2: Pivot to credentials
        result = query_neighbors(
            logger, case_with_data,
            entity_id=alice["id"],
            relationship_types=["has_credential"],
        )
        assert result.is_ok()
        creds = result.ok()
        assert len(creds) == 2

        # Step 3: Check events for each credential
        for cred in creds:
            result = query_events(
                logger, case_with_data,
                target_entity_id=cred["id"],
            )
            assert result.is_ok()

        # Step 4: Record a tool call
        record_tool_call(
            logger, case_with_data,
            case_id="case-e2e", request_id="req-workflow",
            domain="identity", tool_name="search_events",
            request_params={"actor_entity_ids": ["principal_alice"]},
            response_status="success",
            response_body={"status": "success", "items": []},
            duration_ms=120,
        )

        # Step 5: Verify tool call recorded
        result = get_tool_call_history(logger, case_with_data, case_id="case-e2e")
        assert result.is_ok()
        assert len(result.ok()) == 1
        assert result.ok()[0]["tool_name"] == "search_events"
