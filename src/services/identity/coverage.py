"""Coverage report generation for identity domain."""
import logging
from typing import Optional

from src.types.core import CoverageReport, SourceStatus, TimeRange
from src.utils.ulid import generate_ulid


def build_coverage_report(
    logger: logging.Logger,
    domain: str,
    time_range: TimeRange,
    coverage_data: dict,
) -> CoverageReport:
    """Build a CoverageReport from coverage.yaml data."""
    sources = []
    for src in coverage_data.get("sources", []):
        sources.append(SourceStatus(
            source_name=src["source_name"],
            status=src["status"],
            available_fields=src.get("available_fields"),
            missing_fields=src.get("missing_fields"),
            quality_flags=src.get("quality_flags"),
            notes=src.get("notes"),
        ))

    return CoverageReport(
        id=generate_ulid(),
        tlp="GREEN",
        domain=domain,
        time_range=time_range,
        overall_status=coverage_data.get("overall_status", "unknown"),
        sources=sources,
        missing_fields=coverage_data.get("missing_fields"),
        quality_flags=coverage_data.get("quality_flags"),
        notes=coverage_data.get("notes"),
    )


def build_limitations(coverage_data: dict) -> list[str]:
    """Build human-readable limitation strings from coverage data."""
    limitations = []
    for src in coverage_data.get("sources", []):
        if src["status"] == "missing":
            note = src.get("notes", "unavailable")
            limitations.append(f"{src['source_name']}: {note}")
        elif src["status"] == "partial":
            note = src.get("notes", "incomplete")
            limitations.append(f"{src['source_name']}: {note}")
    return limitations


def determine_response_status(overall_status: str) -> str:
    """Map coverage overall_status to response envelope status.

    complete -> success
    partial, missing, unknown -> partial
    """
    if overall_status == "complete":
        return "success"
    return "partial"
