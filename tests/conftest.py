"""Shared test fixtures."""
import logging
from pathlib import Path

import pytest

from src.services.identity.replay_integration import ReplayIdentityIntegration

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "replay" / "scenarios"


def get_test_logger() -> logging.Logger:
    logger = logging.getLogger("blindsight.test")
    logger.setLevel(logging.DEBUG)
    return logger


@pytest.fixture
def test_logger():
    return get_test_logger()


@pytest.fixture
def baseline_scenario_path():
    return FIXTURES_DIR / "credential_change_baseline"


@pytest.fixture
def baseline_integration(baseline_scenario_path, test_logger):
    return ReplayIdentityIntegration(
        scenario_path=baseline_scenario_path,
        logger=test_logger,
    )


ALL_SCENARIO_NAMES = [
    "credential_change_baseline",
    "credential_change_degraded_retention_gap",
    "credential_change_degraded_missing_fields",
    "credential_change_degraded_missing_mfa",
]


def scenario_path_for(name: str) -> Path:
    return FIXTURES_DIR / name
