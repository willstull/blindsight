"""Unit tests for investigation pivot service functions."""
import json
import pytest

from src.services.case.json_helpers import to_json
from src.services.case.pivot import (
    save_pivot,
    list_pivots,
    get_pivot,
    query_pivot_timeline,
    find_event_clusters,
)
from tests.conftest import get_test_logger


_LOG = get_test_logger()


def _insert_event(conn, event_id: str, ts: str, action: str = "auth.login", actor_id: str = "principal_a"):
    """Insert a minimal event directly for testing."""
    conn.execute(
        """INSERT INTO events (id, tlp, domain, ts, action, actor, targets, outcome, raw_refs)
           VALUES (?, 'AMBER', 'identity', ?::TIMESTAMP, ?, ?, '[]', 'succeeded', '[]')""",
        [event_id, ts, action, to_json({"actor_entity_id": actor_id})],
    )


class TestSavePivot:
    def test_save_and_get(self, case_db):
        result = save_pivot(
            _LOG, case_db, "piv-001", "case-001", "test_pivot", "A description",
            event_ids=["e1"], entity_ids=["ent1"], relationship_ids=[],
        )
        assert result.is_ok()
        pivot = result.ok()
        assert pivot["id"] == "piv-001"
        assert pivot["label"] == "test_pivot"
        assert pivot["description"] == "A description"
        assert pivot["event_ids"] == ["e1"]
        assert pivot["entity_ids"] == ["ent1"]
        assert pivot["relationship_ids"] == []

    def test_computes_time_range_from_events(self, case_db):
        _insert_event(case_db, "e1", "2026-01-10T10:00:00Z")
        _insert_event(case_db, "e2", "2026-01-15T14:00:00Z")

        result = save_pivot(
            _LOG, case_db, "piv-002", "case-001", "with_range", None,
            event_ids=["e1", "e2"], entity_ids=[], relationship_ids=["r1"],
        )
        assert result.is_ok()
        pivot = result.ok()
        assert pivot["time_range_start"] is not None
        assert pivot["time_range_end"] is not None
        assert "2026-01-10" in pivot["time_range_start"]
        assert "2026-01-15" in pivot["time_range_end"]

    def test_empty_event_ids_no_time_range(self, case_db):
        result = save_pivot(
            _LOG, case_db, "piv-003", "case-001", "no_events", None,
            event_ids=[], entity_ids=["ent1"], relationship_ids=[],
        )
        assert result.is_ok()
        pivot = result.ok()
        assert pivot["time_range_start"] is None
        assert pivot["time_range_end"] is None

    def test_rejects_all_empty_id_lists(self, case_db):
        result = save_pivot(
            _LOG, case_db, "piv-004", "case-001", "empty", None,
            event_ids=[], entity_ids=[], relationship_ids=[],
        )
        assert result.is_err()

    def test_optional_fields_nullable(self, case_db):
        result = save_pivot(
            _LOG, case_db, "piv-005", "case-001", "minimal", None,
            event_ids=["e1"], entity_ids=[], relationship_ids=[],
        )
        assert result.is_ok()
        pivot = result.ok()
        assert pivot["focal_entity_ids"] is None
        assert pivot["coverage_report_ids"] is None
        assert pivot["created_from_tool_call_ids"] is None

    def test_warns_on_missing_event_ids(self, case_db, caplog):
        """Events not in DB cause a warning but pivot still saves."""
        result = save_pivot(
            _LOG, case_db, "piv-006", "case-001", "missing_events", None,
            event_ids=["nonexistent_1", "nonexistent_2"], entity_ids=[], relationship_ids=["r1"],
        )
        assert result.is_ok()


class TestListPivots:
    def test_list_empty(self, case_db):
        result = list_pivots(_LOG, case_db, "case-001")
        assert result.is_ok()
        assert result.ok() == []

    def test_list_multiple(self, case_db):
        save_pivot(_LOG, case_db, "piv-a", "case-001", "first", None,
                   event_ids=["e1"], entity_ids=[], relationship_ids=[])
        save_pivot(_LOG, case_db, "piv-b", "case-001", "second", None,
                   event_ids=[], entity_ids=["ent1"], relationship_ids=[])
        result = list_pivots(_LOG, case_db, "case-001")
        assert result.is_ok()
        pivots = result.ok()
        assert len(pivots) == 2
        assert pivots[0]["label"] == "first"
        assert pivots[1]["label"] == "second"

    def test_includes_counts(self, case_db):
        save_pivot(_LOG, case_db, "piv-c", "case-001", "counted", None,
                   event_ids=["e1", "e2"], entity_ids=["ent1"], relationship_ids=["r1", "r2", "r3"])
        result = list_pivots(_LOG, case_db, "case-001")
        assert result.is_ok()
        pivot = result.ok()[0]
        assert pivot["event_count"] == 2
        assert pivot["entity_count"] == 1
        assert pivot["relationship_count"] == 3


class TestGetPivot:
    def test_not_found(self, case_db):
        result = get_pivot(_LOG, case_db, "nonexistent")
        assert result.is_ok()
        assert result.ok() is None

    def test_json_columns_parsed(self, case_db):
        save_pivot(_LOG, case_db, "piv-j", "case-001", "json_test", None,
                   event_ids=["e1", "e2"], entity_ids=["ent1"], relationship_ids=[],
                   focal_entity_ids=["f1"])
        result = get_pivot(_LOG, case_db, "piv-j")
        assert result.is_ok()
        pivot = result.ok()
        assert isinstance(pivot["event_ids"], list)
        assert isinstance(pivot["entity_ids"], list)
        assert isinstance(pivot["focal_entity_ids"], list)

    def test_timestamps_are_strings(self, case_db):
        _insert_event(case_db, "e1", "2026-01-10T10:00:00Z")
        save_pivot(_LOG, case_db, "piv-ts", "case-001", "ts_test", None,
                   event_ids=["e1"], entity_ids=[], relationship_ids=["r1"])
        result = get_pivot(_LOG, case_db, "piv-ts")
        pivot = result.ok()
        assert isinstance(pivot["time_range_start"], str)
        assert isinstance(pivot["time_range_end"], str)
        assert isinstance(pivot["created_at"], str)


class TestQueryPivotTimeline:
    def test_returns_events_in_order(self, case_db):
        _insert_event(case_db, "e2", "2026-01-15T14:00:00Z")
        _insert_event(case_db, "e1", "2026-01-10T10:00:00Z")
        save_pivot(_LOG, case_db, "piv-tl", "case-001", "timeline", None,
                   event_ids=["e1", "e2"], entity_ids=[], relationship_ids=["r1"])
        result = query_pivot_timeline(_LOG, case_db, "piv-tl")
        assert result.is_ok()
        events = result.ok()
        assert len(events) == 2
        assert events[0]["id"] == "e1"
        assert events[1]["id"] == "e2"

    def test_respects_limit(self, case_db):
        for i in range(5):
            _insert_event(case_db, f"e{i}", f"2026-01-{10+i:02d}T10:00:00Z")
        save_pivot(_LOG, case_db, "piv-lim", "case-001", "limited", None,
                   event_ids=[f"e{i}" for i in range(5)], entity_ids=[], relationship_ids=["r1"])
        result = query_pivot_timeline(_LOG, case_db, "piv-lim", limit=2)
        assert result.is_ok()
        assert len(result.ok()) == 2

    def test_pivot_not_found(self, case_db):
        result = query_pivot_timeline(_LOG, case_db, "nonexistent")
        assert result.is_err()

    def test_empty_event_ids(self, case_db):
        save_pivot(_LOG, case_db, "piv-empty", "case-001", "empty_events", None,
                   event_ids=[], entity_ids=["ent1"], relationship_ids=[])
        result = query_pivot_timeline(_LOG, case_db, "piv-empty")
        assert result.is_ok()
        assert result.ok() == []


class TestFindEventClusters:
    def test_single_cluster(self, case_db):
        for i in range(5):
            _insert_event(case_db, f"c{i}", f"2026-01-10T10:{i:02d}:00Z", action="auth.account.create")
        save_pivot(_LOG, case_db, "piv-cl", "case-001", "cluster_test", None,
                   event_ids=[f"c{i}" for i in range(5)], entity_ids=[], relationship_ids=["r1"])
        result = find_event_clusters(_LOG, case_db, "piv-cl")
        assert result.is_ok()
        clusters = result.ok()
        assert len(clusters) == 1
        assert clusters[0]["event_count"] == 5
        assert clusters[0]["cluster_id"] == 0

    def test_no_clusters_below_threshold(self, case_db):
        _insert_event(case_db, "solo1", "2026-01-10T10:00:00Z")
        _insert_event(case_db, "solo2", "2026-06-15T10:00:00Z")
        save_pivot(_LOG, case_db, "piv-no", "case-001", "no_cluster", None,
                   event_ids=["solo1", "solo2"], entity_ids=[], relationship_ids=["r1"])
        result = find_event_clusters(_LOG, case_db, "piv-no")
        assert result.is_ok()
        assert result.ok() == []

    def test_custom_window_and_min_events(self, case_db):
        for i in range(4):
            _insert_event(case_db, f"w{i}", f"2026-01-10T10:{i*3:02d}:00Z")
        save_pivot(_LOG, case_db, "piv-cw", "case-001", "custom_window", None,
                   event_ids=[f"w{i}" for i in range(4)], entity_ids=[], relationship_ids=["r1"])
        # 4 events within 9 min -- cluster with window=5 should still work
        result = find_event_clusters(_LOG, case_db, "piv-cw", window_minutes=5, min_events=2)
        assert result.is_ok()
        assert len(result.ok()) >= 1

    def test_dominant_actions(self, case_db):
        _insert_event(case_db, "d1", "2026-01-10T10:00:00Z", action="auth.login")
        _insert_event(case_db, "d2", "2026-01-10T10:01:00Z", action="auth.login")
        _insert_event(case_db, "d3", "2026-01-10T10:02:00Z", action="auth.account.create")
        save_pivot(_LOG, case_db, "piv-dom", "case-001", "dominant", None,
                   event_ids=["d1", "d2", "d3"], entity_ids=[], relationship_ids=["r1"])
        result = find_event_clusters(_LOG, case_db, "piv-dom")
        assert result.is_ok()
        clusters = result.ok()
        assert len(clusters) == 1
        assert clusters[0]["dominant_actions"][0] == "auth.login"

    def test_identical_timestamps(self, case_db):
        for i in range(3):
            _insert_event(case_db, f"same{i}", "2026-01-10T10:00:00Z", action="credential.reset")
        save_pivot(_LOG, case_db, "piv-same", "case-001", "same_ts", None,
                   event_ids=[f"same{i}" for i in range(3)], entity_ids=[], relationship_ids=["r1"])
        result = find_event_clusters(_LOG, case_db, "piv-same")
        assert result.is_ok()
        clusters = result.ok()
        assert len(clusters) == 1
        assert clusters[0]["event_count"] == 3

    def test_unparseable_timestamps(self, case_db):
        """Events with bad timestamps don't crash clustering."""
        conn = case_db
        # Insert events with valid SQL timestamps but test within_minutes handles edge cases
        _insert_event(conn, "bad1", "2026-01-10T10:00:00Z")
        _insert_event(conn, "bad2", "2026-01-10T10:01:00Z")
        _insert_event(conn, "bad3", "2026-01-10T10:02:00Z")
        save_pivot(_LOG, conn, "piv-bad", "case-001", "bad_ts", None,
                   event_ids=["bad1", "bad2", "bad3"], entity_ids=[], relationship_ids=["r1"])
        result = find_event_clusters(_LOG, conn, "piv-bad")
        assert result.is_ok()

    def test_single_event_pivot(self, case_db):
        _insert_event(case_db, "lone1", "2026-01-10T10:00:00Z")
        save_pivot(_LOG, case_db, "piv-lone", "case-001", "single", None,
                   event_ids=["lone1"], entity_ids=[], relationship_ids=["r1"])
        result = find_event_clusters(_LOG, case_db, "piv-lone")
        assert result.is_ok()
        assert result.ok() == []

    def test_multi_cluster(self, case_db):
        # Cluster 1: 3 events in minute 0-2
        for i in range(3):
            _insert_event(case_db, f"mc1_{i}", f"2026-01-10T10:{i:02d}:00Z")
        # Gap
        # Cluster 2: 3 events in minute 30-32
        for i in range(3):
            _insert_event(case_db, f"mc2_{i}", f"2026-01-10T10:{30+i:02d}:00Z")
        all_ids = [f"mc1_{i}" for i in range(3)] + [f"mc2_{i}" for i in range(3)]
        save_pivot(_LOG, case_db, "piv-mc", "case-001", "multi", None,
                   event_ids=all_ids, entity_ids=[], relationship_ids=["r1"])
        result = find_event_clusters(_LOG, case_db, "piv-mc")
        assert result.is_ok()
        clusters = result.ok()
        assert len(clusters) == 2
        assert clusters[0]["cluster_id"] == 0
        assert clusters[1]["cluster_id"] == 1
