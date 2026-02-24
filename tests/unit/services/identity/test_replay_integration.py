"""Unit tests for ReplayIdentityIntegration."""
import pytest

from src.types.core import TimeRange
from tests.conftest import get_test_logger


JAN_RANGE = TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z")


class TestSearchEvents:
    async def test_all_events_in_range(self, baseline_integration):
        result = await baseline_integration.search_events(time_range=JAN_RANGE)
        assert len(result.events) == 52

    async def test_filter_by_single_action(self, baseline_integration):
        result = await baseline_integration.search_events(
            time_range=JAN_RANGE,
            actions=["credential.reset"],
        )
        assert len(result.events) == 1
        assert result.events[0].action == "credential.reset"

    async def test_filter_by_multiple_actions(self, baseline_integration):
        result = await baseline_integration.search_events(
            time_range=JAN_RANGE,
            actions=["credential.reset", "credential.enroll"],
        )
        assert len(result.events) == 2
        actions = {e.action for e in result.events}
        assert actions == {"credential.reset", "credential.enroll"}

    async def test_prefix_matching(self, baseline_integration):
        result = await baseline_integration.search_events(
            time_range=JAN_RANGE,
            actions=["credential.*"],
        )
        assert len(result.events) == 2
        for e in result.events:
            assert e.action.startswith("credential.")

    async def test_filter_by_actor(self, baseline_integration):
        result = await baseline_integration.search_events(
            time_range=JAN_RANGE,
            actor_entity_ids=["principal_alice"],
        )
        assert len(result.events) == 52  # all events are by alice

    async def test_filter_by_nonexistent_actor(self, baseline_integration):
        result = await baseline_integration.search_events(
            time_range=JAN_RANGE,
            actor_entity_ids=["principal_bob"],
        )
        assert len(result.events) == 0

    async def test_narrow_time_range(self, baseline_integration):
        narrow = TimeRange(
            start="2026-01-15T00:00:00Z",
            end="2026-01-15T23:59:59Z",
        )
        result = await baseline_integration.search_events(time_range=narrow)
        assert len(result.events) > 0
        for e in result.events:
            assert e.ts.startswith("2026-01-15")

    async def test_includes_referenced_entities(self, baseline_integration):
        result = await baseline_integration.search_events(
            time_range=JAN_RANGE,
            actions=["credential.reset"],
        )
        entity_ids = {e.id for e in result.entities}
        # Should include actor and target
        assert "principal_alice" in entity_ids
        assert "credential_alice_pw" in entity_ids

    async def test_limit(self, baseline_integration):
        result = await baseline_integration.search_events(
            time_range=JAN_RANGE,
            limit=5,
        )
        assert len(result.events) == 5

    async def test_coverage_present(self, baseline_integration):
        result = await baseline_integration.search_events(time_range=JAN_RANGE)
        assert result.coverage is not None
        assert result.coverage.overall_status == "complete"
        assert result.coverage.domain == "identity"


class TestGetEntity:
    async def test_found(self, baseline_integration):
        result = await baseline_integration.get_entity("principal_alice")
        assert len(result.entities) == 1
        assert result.entities[0].id == "principal_alice"
        assert result.entities[0].entity_type == "principal"

    async def test_not_found(self, baseline_integration):
        result = await baseline_integration.get_entity("nonexistent")
        assert len(result.entities) == 0

    async def test_coverage_present(self, baseline_integration):
        result = await baseline_integration.get_entity("principal_alice")
        assert result.coverage is not None


class TestGetNeighbors:
    async def test_principal_neighbors(self, baseline_integration):
        result = await baseline_integration.get_neighbors("principal_alice")
        # 5 sessions (authenticated_as -> principal) + 2 credentials (has_credential from principal)
        assert len(result.entities) == 7
        assert len(result.relationships) == 7

    async def test_bidirectional(self, baseline_integration):
        """Verify traversal works in both directions."""
        result = await baseline_integration.get_neighbors("session_01")
        entity_ids = {e.id for e in result.entities}
        # session_01 -> principal_alice (authenticated_as)
        # session_01 -> device_01 (uses_device)
        assert "principal_alice" in entity_ids
        assert "device_01" in entity_ids

    async def test_filter_by_relationship_type(self, baseline_integration):
        result = await baseline_integration.get_neighbors(
            "principal_alice",
            relationship_types=["has_credential"],
        )
        assert len(result.entities) == 2
        kinds = {e.kind for e in result.entities}
        assert "password" in kinds
        assert "mfa_totp" in kinds

    async def test_nonexistent_entity(self, baseline_integration):
        result = await baseline_integration.get_neighbors("nonexistent")
        assert len(result.entities) == 0
        assert len(result.relationships) == 0


class TestDescribeCoverage:
    async def test_returns_coverage(self, baseline_integration):
        result = await baseline_integration.describe_coverage(
            time_range=JAN_RANGE,
        )
        assert result.coverage is not None
        assert result.coverage.overall_status == "complete"
        assert len(result.coverage.sources) == 1
        assert result.coverage.sources[0].source_name == "okta"

    async def test_empty_data_arrays(self, baseline_integration):
        result = await baseline_integration.describe_coverage(
            time_range=JAN_RANGE,
        )
        assert result.entities == []
        assert result.events == []
        assert result.relationships == []


class TestDescribeDomain:
    async def test_returns_capabilities(self, baseline_integration):
        info = await baseline_integration.describe_domain()
        assert info["domain"] == "identity"
        assert info["version"] == "0.1.0"
        caps = info["capabilities"]
        assert caps["supports_neighbors"] is True
        assert caps["supports_coverage"] is True
        assert "principal" in caps["supported_entity_types"]


class TestDescribeTypes:
    async def test_returns_types(self, baseline_integration):
        info = await baseline_integration.describe_types()
        assert info["domain"] == "identity"
        types = info["types"]
        assert "principal" in types["entity_type_enum"]
        assert "has_credential" in types["relationship_types"]
        assert "source_ip" in types["context_fields"]
