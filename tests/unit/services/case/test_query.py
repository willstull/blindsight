"""Tests for case store query operations."""
import pytest

from tests.conftest import get_test_logger
from blindsight.services.case.store import open_case_db, create_case
from blindsight.services.case.ingest import (
    ingest_entities, ingest_events, ingest_relationships,
    ingest_coverage_report, record_tool_call,
)
from blindsight.services.case.query import (
    query_entities, query_events, query_neighbors,
    get_timeline, get_tool_call_history,
)
from blindsight.types.core import (
    Entity, ActionEvent, Relationship, CoverageReport,
    Actor, Target, Ref, TimeRange, SourceStatus,
)


@pytest.fixture
def populated_db(tmp_path):
    """DB with baseline data: 3 entities, 3 events, 2 relationships."""
    logger = get_test_logger()
    result = open_case_db(logger, tmp_path / "test.duckdb")
    assert result.is_ok()
    conn = result.ok()
    create_case(logger, conn, "case-001", "Test Case")

    # Entities
    entities = [
        Entity(id="principal_alice", tlp="GREEN", entity_type="principal", kind="user",
               display_name="Alice", refs=[Ref(ref_type="email", system="okta", value="alice@example.com")],
               attributes={"department": "engineering"}),
        Entity(id="cred_alice_pw", tlp="GREEN", entity_type="credential", kind="password",
               display_name="Alice Password", refs=[]),
        Entity(id="session_alice_1", tlp="GREEN", entity_type="session", kind="web_session",
               display_name="Alice Session 1", refs=[]),
    ]
    ingest_entities(logger, conn, entities)

    # Events
    events = [
        ActionEvent(
            id="evt-001", tlp="GREEN", domain="identity",
            ts="2026-01-15T10:00:00Z", action="credential.reset",
            actor=Actor(actor_entity_id="principal_alice"),
            targets=[Target(target_entity_id="cred_alice_pw", role="subject")],
            outcome="succeeded",
            raw_refs=[Ref(ref_type="log_id", system="okta", value="log-001")],
        ),
        ActionEvent(
            id="evt-002", tlp="GREEN", domain="identity",
            ts="2026-01-15T11:00:00Z", action="session.start",
            actor=Actor(actor_entity_id="principal_alice"),
            targets=[Target(target_entity_id="session_alice_1", role="subject")],
            outcome="succeeded", raw_refs=[],
        ),
        ActionEvent(
            id="evt-003", tlp="GREEN", domain="identity",
            ts="2026-01-15T12:00:00Z", action="session.end",
            actor=Actor(actor_entity_id="principal_alice"),
            targets=[], outcome="succeeded", raw_refs=[],
        ),
    ]
    ingest_events(logger, conn, events)

    # Relationships
    rels = [
        Relationship(
            id="rel-001", tlp="GREEN", domain="identity",
            relationship_type="has_credential",
            from_entity_id="principal_alice", to_entity_id="cred_alice_pw",
        ),
        Relationship(
            id="rel-002", tlp="GREEN", domain="identity",
            relationship_type="has_session",
            from_entity_id="principal_alice", to_entity_id="session_alice_1",
        ),
    ]
    ingest_relationships(logger, conn, rels)

    yield conn
    conn.close()


class TestQueryEntities:
    def test_query_all(self, populated_db):
        logger = get_test_logger()
        result = query_entities(logger, populated_db)
        assert result.is_ok()
        assert len(result.ok()) == 3

    def test_filter_by_entity_type(self, populated_db):
        logger = get_test_logger()
        result = query_entities(logger, populated_db, entity_types=["principal"])
        assert result.is_ok()
        entities = result.ok()
        assert len(entities) == 1
        assert entities[0]["id"] == "principal_alice"

    def test_filter_by_kind(self, populated_db):
        logger = get_test_logger()
        result = query_entities(logger, populated_db, kinds=["password"])
        assert result.is_ok()
        assert len(result.ok()) == 1
        assert result.ok()[0]["id"] == "cred_alice_pw"

    def test_filter_by_display_name(self, populated_db):
        logger = get_test_logger()
        result = query_entities(logger, populated_db, display_name_contains="alice")
        assert result.is_ok()
        # "Alice", "Alice Password", "Alice Session 1" all match
        assert len(result.ok()) == 3

    def test_limit(self, populated_db):
        logger = get_test_logger()
        result = query_entities(logger, populated_db, limit=1)
        assert result.is_ok()
        assert len(result.ok()) == 1

    def test_json_columns_parsed(self, populated_db):
        logger = get_test_logger()
        result = query_entities(logger, populated_db, entity_types=["principal"])
        entity = result.ok()[0]
        assert isinstance(entity["refs"], list)
        assert entity["refs"][0]["value"] == "alice@example.com"
        assert isinstance(entity["attributes"], dict)
        assert entity["attributes"]["department"] == "engineering"


class TestQueryEvents:
    def test_query_all(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db)
        assert result.is_ok()
        assert len(result.ok()) == 3

    def test_filter_by_actor(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db, actor_entity_id="principal_alice")
        assert result.is_ok()
        assert len(result.ok()) == 3

    def test_filter_by_target(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db, target_entity_id="cred_alice_pw")
        assert result.is_ok()
        events = result.ok()
        assert len(events) == 1
        assert events[0]["action"] == "credential.reset"

    def test_filter_by_action(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db, actions=["session.start", "session.end"])
        assert result.is_ok()
        assert len(result.ok()) == 2

    def test_filter_by_action_prefix(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db, actions=["credential.*"])
        assert result.is_ok()
        events = result.ok()
        assert len(events) == 1
        assert events[0]["action"] == "credential.reset"

    def test_filter_by_action_mixed(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db, actions=["session.start", "credential.*"])
        assert result.is_ok()
        events = result.ok()
        assert len(events) == 2
        actions = {e["action"] for e in events}
        assert actions == {"session.start", "credential.reset"}

    def test_filter_by_time_range(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db,
                              time_range_start="2026-01-15T10:30:00Z",
                              time_range_end="2026-01-15T11:30:00Z")
        assert result.is_ok()
        assert len(result.ok()) == 1
        assert result.ok()[0]["action"] == "session.start"

    def test_filter_by_outcome(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db, outcome="succeeded")
        assert result.is_ok()
        assert len(result.ok()) == 3

    def test_order_desc(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db)
        events = result.ok()
        # Most recent first
        assert events[0]["id"] == "evt-003"
        assert events[2]["id"] == "evt-001"

    def test_json_columns_parsed(self, populated_db):
        logger = get_test_logger()
        result = query_events(logger, populated_db, actions=["credential.reset"])
        event = result.ok()[0]
        assert isinstance(event["actor"], dict)
        assert event["actor"]["actor_entity_id"] == "principal_alice"
        assert isinstance(event["targets"], list)


class TestQueryNeighbors:
    def test_find_all_neighbors(self, populated_db):
        logger = get_test_logger()
        result = query_neighbors(logger, populated_db, entity_id="principal_alice")
        assert result.is_ok()
        neighbors = result.ok()
        assert len(neighbors) == 2
        neighbor_ids = {n["id"] for n in neighbors}
        assert neighbor_ids == {"cred_alice_pw", "session_alice_1"}

    def test_filter_by_relationship_type(self, populated_db):
        logger = get_test_logger()
        result = query_neighbors(logger, populated_db,
                                 entity_id="principal_alice",
                                 relationship_types=["has_credential"])
        assert result.is_ok()
        assert len(result.ok()) == 1
        assert result.ok()[0]["id"] == "cred_alice_pw"

    def test_direction_field(self, populated_db):
        logger = get_test_logger()
        result = query_neighbors(logger, populated_db, entity_id="principal_alice")
        for n in result.ok():
            assert n["direction"] == "outgoing"

        # From the other direction
        result = query_neighbors(logger, populated_db, entity_id="cred_alice_pw")
        assert result.is_ok()
        assert len(result.ok()) == 1
        assert result.ok()[0]["direction"] == "incoming"

    def test_no_neighbors(self, populated_db):
        logger = get_test_logger()
        # session_alice_1 only has incoming from principal_alice
        result = query_neighbors(logger, populated_db,
                                 entity_id="session_alice_1",
                                 relationship_types=["has_credential"])
        assert result.is_ok()
        assert len(result.ok()) == 0


class TestGetTimeline:
    def test_chronological_order(self, populated_db):
        logger = get_test_logger()
        result = get_timeline(logger, populated_db)
        assert result.is_ok()
        events = result.ok()
        assert len(events) == 3
        # Ascending order
        assert events[0]["id"] == "evt-001"
        assert events[2]["id"] == "evt-003"

    def test_filter_by_time_range(self, populated_db):
        logger = get_test_logger()
        result = get_timeline(logger, populated_db,
                              time_range_start="2026-01-15T10:30:00Z",
                              time_range_end="2026-01-15T11:30:00Z")
        assert result.is_ok()
        assert len(result.ok()) == 1

    def test_filter_by_actor(self, populated_db):
        logger = get_test_logger()
        result = get_timeline(logger, populated_db, actor_entity_id="principal_alice")
        assert result.is_ok()
        assert len(result.ok()) == 3


class TestGetToolCallHistory:
    def test_empty_history(self, populated_db):
        logger = get_test_logger()
        result = get_tool_call_history(logger, populated_db, case_id="case-001")
        assert result.is_ok()
        assert len(result.ok()) == 0

    def test_with_recorded_calls(self, populated_db):
        logger = get_test_logger()
        record_tool_call(logger, populated_db,
                         case_id="case-001", request_id="req-001",
                         domain="identity", tool_name="search_events",
                         request_params={"actions": ["credential.reset"]},
                         response_status="success", response_body={"items": []},
                         duration_ms=50)
        record_tool_call(logger, populated_db,
                         case_id="case-001", request_id="req-002",
                         domain="identity", tool_name="get_entity",
                         request_params={"entity_id": "principal_alice"},
                         response_status="success", response_body={"items": []},
                         duration_ms=30)

        result = get_tool_call_history(logger, populated_db, case_id="case-001")
        assert result.is_ok()
        calls = result.ok()
        assert len(calls) == 2
        # Most recent first
        assert calls[0]["tool_name"] == "get_entity"
        assert calls[1]["tool_name"] == "search_events"
        # JSON parsed
        assert isinstance(calls[0]["request_params"], dict)
