"""Unit tests for app domain replay integration.

Mirrors the identity replay integration test structure.
Uses account_substitution_baseline app fixtures.
"""
import pytest

from blindsight.services.app.replay_integration import ReplayAppIntegration
from blindsight.types.core import TimeRange
from tests.conftest import get_test_logger, FIXTURES_DIR


_SCENARIO = FIXTURES_DIR / "account_substitution_baseline"
_TIME_RANGE = TimeRange(start="2026-03-01T00:00:00Z", end="2026-03-31T23:59:59Z")


@pytest.fixture
def integration():
    return ReplayAppIntegration(_SCENARIO, get_test_logger())


class TestDescribeDomain:
    async def test_returns_app_domain(self, integration):
        result = await integration.describe_domain()
        assert result["domain"] == "app"

    async def test_action_prefix(self, integration):
        result = await integration.describe_domain()
        assert "app." in result["capabilities"]["supported_actions_prefixes"]

    async def test_entity_types(self, integration):
        result = await integration.describe_domain()
        types = result["capabilities"]["supported_entity_types"]
        assert "resource" in types
        assert "principal" in types


class TestDescribeTypes:
    async def test_includes_resource_type(self, integration):
        result = await integration.describe_types()
        assert result["domain"] == "app"
        assert "resource" in result["types"]["entity_type_enum"]


class TestGetEntity:
    async def test_resource_entity(self, integration):
        result = await integration.get_entity("resource_financial_system")
        assert len(result.entities) == 1
        assert result.entities[0].id == "resource_financial_system"
        assert result.entities[0].kind == "application"

    async def test_principal_entity(self, integration):
        result = await integration.get_entity("principal_jef_greenfield")
        assert len(result.entities) == 1
        assert result.entities[0].entity_type == "principal"

    async def test_not_found(self, integration):
        result = await integration.get_entity("nonexistent")
        assert len(result.entities) == 0


class TestSearchEntities:
    async def test_search_financial(self, integration):
        result = await integration.search_entities("financial")
        assert len(result.entities) >= 1
        assert any(e.id == "resource_financial_system" for e in result.entities)

    async def test_filter_by_kind(self, integration):
        result = await integration.search_entities("", kinds=["application"])
        assert all(e.kind == "application" for e in result.entities)
        assert len(result.entities) >= 1


class TestSearchEvents:
    async def test_search_invoice_events(self, integration):
        result = await integration.search_events(
            time_range=_TIME_RANGE,
            actions=["app.invoice.create"],
        )
        assert len(result.events) > 0
        assert all(e.action == "app.invoice.create" for e in result.events)

    async def test_search_by_actor(self, integration):
        result = await integration.search_events(
            time_range=_TIME_RANGE,
            actor_entity_ids=["principal_jef_greenfield"],
        )
        assert len(result.events) > 0
        assert all(e.actor.actor_entity_id == "principal_jef_greenfield" for e in result.events)

    async def test_returns_referenced_entities(self, integration):
        result = await integration.search_events(
            time_range=_TIME_RANGE,
            actions=["app.invoice.create"],
        )
        entity_ids = {e.id for e in result.entities}
        assert "principal_jef_greenfield" in entity_ids or "resource_financial_system" in entity_ids

    async def test_all_events_have_app_domain(self, integration):
        result = await integration.search_events(time_range=_TIME_RANGE)
        assert all(e.domain == "app" for e in result.events)


class TestGetNeighbors:
    async def test_empty_relationships(self, integration):
        """App fixtures have no relationships, so neighbors should be empty."""
        result = await integration.get_neighbors("resource_financial_system")
        assert len(result.relationships) == 0


class TestDescribeCoverage:
    async def test_domain_is_app(self, integration):
        result = await integration.describe_coverage(time_range=_TIME_RANGE)
        assert result.coverage is not None
        assert result.coverage.domain == "app"

    async def test_complete_status(self, integration):
        result = await integration.describe_coverage(time_range=_TIME_RANGE)
        assert result.coverage.overall_status == "complete"
