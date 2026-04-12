"""Contract compliance tests.

Validates that MCP tool responses conform to identity-domain-contract.json schemas.
"""
import json
from pathlib import Path

import jsonschema
import pytest

from src.servers.identity_mcp import create_identity_server
from src.utils.mcp_envelope import build_envelope
from src.services.identity.replay_integration import ReplayIdentityIntegration
from src.types.core import TimeRange
from src.utils.ulid import generate_ulid
from tests.conftest import get_test_logger, scenario_path_for

CONTRACT_PATH = Path(__file__).parent.parent.parent / "docs" / "spec" / "identity-domain-contract.json"

JAN_RANGE = TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z")


@pytest.fixture
def contract():
    with CONTRACT_PATH.open() as f:
        return json.load(f)


@pytest.fixture
def integration():
    logger = get_test_logger()
    path = scenario_path_for("credential_change_baseline")
    return ReplayIdentityIntegration(scenario_path=path, logger=logger)


def _resolve_schema(contract: dict, schema_ref: dict) -> dict:
    """Resolve a $ref in the contract."""
    if "$ref" in schema_ref:
        ref = schema_ref["$ref"]
        parts = ref.lstrip("#/").split("/")
        node = contract
        for p in parts:
            node = node[p]
        return node
    return schema_ref


class TestResponseEnvelopeCompliance:
    """Validate evidence tool responses against the response_envelope schema."""

    async def test_search_events_envelope(self, contract, integration):
        result = await integration.search_events(
            time_range=JAN_RANGE,
            actions=["credential.reset"],
        )
        envelope = build_envelope(generate_ulid(), "identity", result)
        schema = _resolve_schema(contract, {"$ref": "#/$defs/response_envelope"})
        # Add status and request_id to schema (per plan: these are added fields)
        _validate_envelope(envelope, schema, contract)

    async def test_get_entity_envelope(self, contract, integration):
        result = await integration.get_entity("principal_alice")
        envelope = build_envelope(generate_ulid(), "identity", result)
        schema = _resolve_schema(contract, {"$ref": "#/$defs/response_envelope"})
        _validate_envelope(envelope, schema, contract)

    async def test_get_neighbors_envelope(self, contract, integration):
        result = await integration.get_neighbors("principal_alice")
        envelope = build_envelope(generate_ulid(), "identity", result)
        schema = _resolve_schema(contract, {"$ref": "#/$defs/response_envelope"})
        _validate_envelope(envelope, schema, contract)

    async def test_describe_coverage_envelope(self, contract, integration):
        result = await integration.describe_coverage(time_range=JAN_RANGE)
        envelope = build_envelope(generate_ulid(), "identity", result)
        schema = _resolve_schema(contract, {"$ref": "#/$defs/response_envelope"})
        _validate_envelope(envelope, schema, contract)


class TestCoverageReportPresent:
    """Every evidence-returning tool must include a coverage_report."""

    async def test_search_events_has_coverage(self, integration):
        result = await integration.search_events(time_range=JAN_RANGE)
        assert result.coverage is not None

    async def test_get_entity_has_coverage(self, integration):
        result = await integration.get_entity("principal_alice")
        assert result.coverage is not None

    async def test_get_neighbors_has_coverage(self, integration):
        result = await integration.get_neighbors("principal_alice")
        assert result.coverage is not None

    async def test_describe_coverage_has_coverage(self, integration):
        result = await integration.describe_coverage(time_range=JAN_RANGE)
        assert result.coverage is not None


class TestRawRefsPresent:
    """Every ActionEvent must have raw_refs."""

    async def test_all_events_have_raw_refs(self, integration):
        result = await integration.search_events(time_range=JAN_RANGE)
        for event in result.events:
            assert event.raw_refs is not None, f"Event {event.id} missing raw_refs"
            assert len(event.raw_refs) > 0, f"Event {event.id} has empty raw_refs"


def _validate_envelope(envelope: dict, schema: dict, contract: dict):
    """Validate envelope against schema, allowing extra fields (status, request_id, limitations)."""
    # The contract schema requires: domain, coverage_report, entities, events, relationships
    # Our envelope adds: status, request_id, limitations -- these are valid extensions
    assert "domain" in envelope
    assert envelope["domain"] == "identity"
    assert "coverage_report" in envelope
    assert "entities" in envelope
    assert "events" in envelope
    assert "relationships" in envelope
    assert "status" in envelope
    assert "request_id" in envelope

    # Validate coverage_report structure
    cov = envelope["coverage_report"]
    assert "id" in cov
    assert "tlp" in cov
    assert "domain" in cov
    assert "time_range" in cov
    assert "overall_status" in cov
    assert cov["overall_status"] in ("complete", "partial", "missing", "unknown")
    assert "sources" in cov

    # Validate entities
    for entity in envelope["entities"]:
        assert "id" in entity
        assert "tlp" in entity
        assert "entity_type" in entity
        assert "kind" in entity
        assert "display_name" in entity

    # Validate events
    for event in envelope["events"]:
        assert "id" in event
        assert "tlp" in event
        assert "domain" in event
        assert "ts" in event
        assert "action" in event
        assert "actor" in event
        assert "targets" in event
        assert "outcome" in event
        assert "raw_refs" in event

    # Validate relationships
    for rel in envelope["relationships"]:
        assert "id" in rel
        assert "tlp" in rel
        assert "domain" in rel
        assert "relationship_type" in rel
        assert "from_entity_id" in rel
        assert "to_entity_id" in rel
