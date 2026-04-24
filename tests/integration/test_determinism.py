"""Determinism tests: same query 3x produces identical output (minus ULIDs)."""
import json
import re

import pytest

from blindsight.utils.mcp_envelope import build_envelope
from blindsight.services.identity.replay_integration import ReplayIdentityIntegration
from blindsight.types.core import TimeRange
from blindsight.utils.ulid import generate_ulid
from tests.conftest import get_test_logger, scenario_path_for


ULID_PATTERN = re.compile(r"[0-9A-Z]{26}")


def _strip_ulids(d: dict) -> dict:
    """Replace all ULID-like strings with a placeholder for comparison."""
    s = json.dumps(d, sort_keys=True)
    s = ULID_PATTERN.sub("__ULID__", s)
    return json.loads(s)


@pytest.fixture
def integration():
    logger = get_test_logger()
    path = scenario_path_for("credential_change_baseline")
    return ReplayIdentityIntegration(scenario_path=path, logger=logger)


class TestDeterminism:
    async def test_search_events_deterministic(self, integration):
        time_range = TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z")
        outputs = []
        for _ in range(3):
            result = await integration.search_events(
                time_range=time_range,
                actions=["credential.reset", "credential.enroll"],
            )
            envelope = build_envelope(generate_ulid(), "identity", result)
            outputs.append(_strip_ulids(envelope))

        assert outputs[0] == outputs[1], "Run 1 and 2 differ"
        assert outputs[1] == outputs[2], "Run 2 and 3 differ"

    async def test_get_entity_deterministic(self, integration):
        outputs = []
        for _ in range(3):
            result = await integration.get_entity("principal_alice")
            envelope = build_envelope(generate_ulid(), "identity", result)
            outputs.append(_strip_ulids(envelope))

        assert outputs[0] == outputs[1]
        assert outputs[1] == outputs[2]

    async def test_get_neighbors_deterministic(self, integration):
        outputs = []
        for _ in range(3):
            result = await integration.get_neighbors("principal_alice")
            envelope = build_envelope(generate_ulid(), "identity", result)
            # Sort entities and relationships for stable comparison
            d = envelope.copy()
            d["entities"] = sorted(d["entities"], key=lambda e: e["id"])
            d["relationships"] = sorted(d["relationships"], key=lambda r: r["id"])
            outputs.append(_strip_ulids(d))

        assert outputs[0] == outputs[1]
        assert outputs[1] == outputs[2]
