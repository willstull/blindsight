"""Shared test fixtures."""
import logging
from pathlib import Path

import pytest

from src.services.identity.replay_integration import ReplayIdentityIntegration
from src.services.case.store import open_case_db, create_case

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


@pytest.fixture
def case_db(tmp_path):
    """Open a fresh case DB for each test."""
    logger = get_test_logger()
    result = open_case_db(logger, tmp_path / "test.duckdb")
    assert result.is_ok()
    conn = result.ok()
    create_case(logger, conn, "case-001", "Test Case")
    yield conn
    conn.close()


@pytest.fixture
def cases_dir(tmp_path):
    """Temporary directory for case DB files."""
    d = tmp_path / "cases"
    d.mkdir()
    return d
