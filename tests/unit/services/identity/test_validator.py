"""Unit tests for identity domain validators."""
import pytest
from tests.conftest import get_test_logger
from src.services.identity.validator import (
    validate_time_range,
    validate_entity_id,
    validate_limit,
)


@pytest.fixture
def logger():
    return get_test_logger()


class TestValidateTimeRange:
    def test_valid_range(self, logger):
        result = validate_time_range(logger, "2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z")
        assert result.is_ok()
        tr = result.ok()
        assert tr.start == "2026-01-01T00:00:00Z"
        assert tr.end == "2026-01-31T23:59:59Z"

    def test_missing_start(self, logger):
        result = validate_time_range(logger, "", "2026-01-31T23:59:59Z")
        assert result.is_err()
        assert result.err().code == "time_range_required"

    def test_missing_end(self, logger):
        result = validate_time_range(logger, "2026-01-01T00:00:00Z", "")
        assert result.is_err()
        assert result.err().code == "time_range_required"

    def test_invalid_timestamp(self, logger):
        result = validate_time_range(logger, "not-a-date", "2026-01-31T23:59:59Z")
        assert result.is_err()
        assert result.err().code == "invalid_timestamp"

    def test_start_after_end(self, logger):
        result = validate_time_range(logger, "2026-02-01T00:00:00Z", "2026-01-01T00:00:00Z")
        assert result.is_err()
        assert result.err().code == "invalid_time_range"

    def test_range_too_large(self, logger):
        result = validate_time_range(
            logger,
            "2025-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
            max_days=90,
        )
        assert result.is_err()
        assert result.err().code == "time_range_too_large"


class TestValidateEntityId:
    def test_valid(self, logger):
        result = validate_entity_id(logger, "principal_alice")
        assert result.is_ok()
        assert result.ok() == "principal_alice"

    def test_empty(self, logger):
        result = validate_entity_id(logger, "")
        assert result.is_err()
        assert result.err().code == "entity_id_required"

    def test_none(self, logger):
        result = validate_entity_id(logger, None)
        assert result.is_err()

    def test_whitespace_stripped(self, logger):
        result = validate_entity_id(logger, "  principal_alice  ")
        assert result.is_ok()
        assert result.ok() == "principal_alice"


class TestValidateLimit:
    def test_valid(self, logger):
        result = validate_limit(logger, 100)
        assert result.is_ok()
        assert result.ok() == 100

    def test_none_uses_default(self, logger):
        result = validate_limit(logger, None, max_limit=500)
        assert result.is_ok()
        assert result.ok() == 500

    def test_zero(self, logger):
        result = validate_limit(logger, 0)
        assert result.is_err()
        assert result.err().code == "invalid_limit"

    def test_negative(self, logger):
        result = validate_limit(logger, -1)
        assert result.is_err()

    def test_clamped_to_max(self, logger):
        result = validate_limit(logger, 5000, max_limit=2000)
        assert result.is_ok()
        assert result.ok() == 2000
