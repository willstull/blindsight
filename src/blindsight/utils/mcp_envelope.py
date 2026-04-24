"""Shared MCP response envelope builders for domain servers."""
from blindsight.utils.coverage import determine_response_status
from blindsight.types.envelope import IntegrationResult, ResponseEnvelope
from blindsight.types.errors import PipelineError


def build_envelope(
    request_id: str,
    domain: str,
    result: IntegrationResult,
) -> dict:
    """Build a ResponseEnvelope dict from an IntegrationResult."""
    status = "success"
    if result.coverage:
        status = determine_response_status(result.coverage.overall_status)

    envelope = ResponseEnvelope(
        status=status,
        domain=domain,
        request_id=request_id,
        coverage_report=result.coverage,
        entities=result.entities,
        events=result.events,
        relationships=result.relationships,
        limitations=result.limitations if result.limitations else [],
    )
    return envelope.to_dict()


def build_error_envelope(
    request_id: str,
    domain: str,
    code: str,
    message: str,
) -> dict:
    """Build an error ResponseEnvelope."""
    envelope = ResponseEnvelope(
        status="error",
        domain=domain,
        request_id=request_id,
        error=PipelineError(code=code, message=message, severity="error"),
    )
    return envelope.to_dict()
