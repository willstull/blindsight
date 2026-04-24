"""Response envelope types.

IntegrationResult: returned by integration methods (transport-agnostic).
ResponseEnvelope: built by MCP tool handlers (wire format).
"""
from typing import Optional

from pydantic import BaseModel, Field

from blindsight.types.core import Entity, ActionEvent, Relationship, CoverageReport
from blindsight.types.errors import PipelineError


class IntegrationResult(BaseModel):
    """Returned by DomainIntegration evidence methods."""
    entities: list[Entity] = Field(default_factory=list)
    events: list[ActionEvent] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    coverage: Optional[CoverageReport] = None
    limitations: list[str] = Field(default_factory=list)


class ResponseEnvelope(BaseModel):
    """Wire format returned by MCP tool handlers."""
    status: str  # success | partial | error
    domain: str
    request_id: str
    coverage_report: Optional[CoverageReport] = None
    entities: list[Entity] = Field(default_factory=list)
    events: list[ActionEvent] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    error: Optional[PipelineError] = None
    limitations: list[str] = Field(default_factory=list)
    next_page_token: Optional[str] = None

    def to_dict(self) -> dict:
        """Recursive model dump with None stripping."""
        return self.model_dump(exclude_none=True)
