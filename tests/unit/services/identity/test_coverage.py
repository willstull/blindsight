"""Unit tests for coverage report generation."""
import pytest
from tests.conftest import get_test_logger
from blindsight.utils.coverage import (
    build_coverage_report,
    build_limitations,
    determine_response_status,
)
from blindsight.types.core import TimeRange


@pytest.fixture
def logger():
    return get_test_logger()


JAN_RANGE = TimeRange(start="2026-01-01T00:00:00Z", end="2026-01-31T23:59:59Z")


class TestBuildCoverageReport:
    def test_complete(self, logger):
        data = {
            "overall_status": "complete",
            "sources": [{"source_name": "okta", "status": "complete"}],
        }
        report = build_coverage_report(logger, "identity", JAN_RANGE, data)
        assert report.overall_status == "complete"
        assert report.domain == "identity"
        assert report.time_range.start == JAN_RANGE.start
        assert len(report.sources) == 1
        assert report.sources[0].source_name == "okta"
        assert report.id  # has a ULID

    def test_partial_with_notes(self, logger):
        data = {
            "overall_status": "partial",
            "sources": [
                {"source_name": "okta", "status": "complete"},
                {"source_name": "mfa_provider", "status": "missing", "notes": "MFA logs unavailable"},
            ],
            "notes": "MFA provider logs unavailable",
        }
        report = build_coverage_report(logger, "identity", JAN_RANGE, data)
        assert report.overall_status == "partial"
        assert len(report.sources) == 2
        assert report.notes == "MFA provider logs unavailable"


class TestBuildLimitations:
    def test_missing_source(self):
        data = {
            "sources": [
                {"source_name": "okta", "status": "complete"},
                {"source_name": "mfa_provider", "status": "missing", "notes": "MFA logs unavailable"},
            ]
        }
        limits = build_limitations(data)
        assert len(limits) == 1
        assert "mfa_provider" in limits[0]

    def test_partial_source(self):
        data = {
            "sources": [
                {"source_name": "auth_stream", "status": "partial", "notes": "Retention gap Jan 10-20"},
            ]
        }
        limits = build_limitations(data)
        assert len(limits) == 1
        assert "auth_stream" in limits[0]

    def test_complete_no_limitations(self):
        data = {
            "sources": [{"source_name": "okta", "status": "complete"}]
        }
        limits = build_limitations(data)
        assert limits == []


class TestDetermineResponseStatus:
    def test_complete_to_success(self):
        assert determine_response_status("complete") == "success"

    def test_partial_to_partial(self):
        assert determine_response_status("partial") == "partial"

    def test_missing_to_partial(self):
        assert determine_response_status("missing") == "partial"

    def test_unknown_to_partial(self):
        assert determine_response_status("unknown") == "partial"
