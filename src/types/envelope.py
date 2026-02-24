"""Response envelope types.

IntegrationResult: returned by integration methods (transport-agnostic).
ResponseEnvelope: built by MCP tool handlers (wire format).
"""
from dataclasses import dataclass, field, asdict
from typing import Optional

from src.types.core import Entity, ActionEvent, Relationship, CoverageReport
from src.types.errors import PipelineError


@dataclass
class IntegrationResult:
    """Returned by DomainIntegration evidence methods."""
    entities: list[Entity] = field(default_factory=list)
    events: list[ActionEvent] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    coverage: Optional[CoverageReport] = None
    limitations: list[str] = field(default_factory=list)


@dataclass
class ResponseEnvelope:
    """Wire format returned by MCP tool handlers."""
    status: str  # success | partial | error
    domain: str
    request_id: str
    coverage_report: Optional[CoverageReport] = None
    entities: list[Entity] = field(default_factory=list)
    events: list[ActionEvent] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    error: Optional[PipelineError] = None
    limitations: list[str] = field(default_factory=list)
    next_page_token: Optional[str] = None

    def to_dict(self) -> dict:
        """Recursive asdict with None stripping."""
        return _strip_nones(asdict(self))


def _strip_nones(obj):
    """Recursively remove None values from dicts."""
    if isinstance(obj, dict):
        return {k: _strip_nones(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_nones(item) for item in obj]
    return obj
