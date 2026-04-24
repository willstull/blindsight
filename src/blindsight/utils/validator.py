"""Request validation for domain MCP server tools."""
import logging
from typing import Optional

from src.types.core import TimeRange
from src.types.errors import ValidationIssue
from src.types.result import Result, Ok, Err

MAX_TIME_RANGE_DAYS = 90
MAX_LIMIT = 2000


def validate_time_range(
    logger: logging.Logger,
    start: str,
    end: str,
    max_days: int = MAX_TIME_RANGE_DAYS,
) -> Result[TimeRange, ValidationIssue]:
    """Validate and parse a time range from RFC3339 strings."""
    from src.utils.time import parse_rfc3339

    if not start or not end:
        return Err(ValidationIssue(
            code="time_range_required",
            message="Both start and end timestamps are required",
            severity="error",
            field="time_range",
        ))

    try:
        start_dt = parse_rfc3339(start)
        end_dt = parse_rfc3339(end)
    except (ValueError, TypeError) as exc:
        return Err(ValidationIssue(
            code="invalid_timestamp",
            message=f"Invalid RFC3339 timestamp: {exc}",
            severity="error",
            field="time_range",
        ))

    if start_dt > end_dt:
        return Err(ValidationIssue(
            code="invalid_time_range",
            message="start must be before end",
            severity="error",
            field="time_range",
        ))

    delta = end_dt - start_dt
    if delta.days > max_days:
        return Err(ValidationIssue(
            code="time_range_too_large",
            message=f"Time range exceeds {max_days} days ({delta.days} days requested)",
            severity="error",
            field="time_range",
        ))

    return Ok(TimeRange(start=start, end=end))


def validate_entity_id(
    logger: logging.Logger,
    entity_id: Optional[str],
) -> Result[str, ValidationIssue]:
    """Validate that entity_id is a non-empty string."""
    if not entity_id or not entity_id.strip():
        return Err(ValidationIssue(
            code="entity_id_required",
            message="entity_id is required and must be non-empty",
            severity="error",
            field="entity_id",
        ))
    return Ok(entity_id.strip())


def validate_limit(
    logger: logging.Logger,
    limit: Optional[int],
    max_limit: int = MAX_LIMIT,
) -> Result[int, ValidationIssue]:
    """Validate and clamp limit parameter."""
    if limit is None:
        return Ok(max_limit)
    if limit < 1:
        return Err(ValidationIssue(
            code="invalid_limit",
            message="limit must be >= 1",
            severity="error",
            field="limit",
        ))
    return Ok(min(limit, max_limit))
