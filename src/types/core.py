"""Core data types from ontology.yaml v0.1.

Pure data structures -- no business logic.
Timestamps are strings (RFC3339) to match NDJSON fixture format directly.
"""
from typing import Optional

from pydantic import BaseModel, Field


class Ref(BaseModel):
    ref_type: str
    system: str
    value: str
    url: Optional[str] = None
    observed_at: Optional[str] = None


class TimeRange(BaseModel):
    start: str  # RFC3339
    end: str


class Actor(BaseModel):
    actor_entity_id: str


class Target(BaseModel):
    target_entity_id: str
    role: Optional[str] = None


class Entity(BaseModel):
    id: str
    tlp: str
    entity_type: str
    kind: str
    display_name: str
    refs: list[Ref] = Field(default_factory=list)
    attributes: Optional[dict] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    confidence: Optional[float] = None


class ActionEvent(BaseModel):
    id: str
    tlp: str
    domain: str
    ts: str  # RFC3339
    action: str
    actor: Actor
    targets: list[Target] = Field(default_factory=list)
    outcome: str = "unknown"
    raw_refs: list[Ref] = Field(default_factory=list)
    context: Optional[dict] = None
    related_entity_ids: Optional[list[str]] = None
    ingested_at: Optional[str] = None


class Relationship(BaseModel):
    id: str
    tlp: str
    domain: str
    relationship_type: str
    from_entity_id: str
    to_entity_id: str
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    evidence_refs: Optional[list[Ref]] = None


class SourceStatus(BaseModel):
    source_name: str
    status: str  # complete | partial | missing | unknown
    available_fields: Optional[list[str]] = None
    missing_fields: Optional[list[str]] = None
    quality_flags: Optional[list[str]] = None
    notes: Optional[str] = None


class CoverageReport(BaseModel):
    id: str
    tlp: str
    domain: str
    time_range: TimeRange
    overall_status: str  # complete | partial | missing | unknown
    sources: list[SourceStatus] = Field(default_factory=list)
    missing_fields: Optional[list[str]] = None
    data_latency_seconds: Optional[float] = None
    quality_flags: Optional[list[str]] = None
    notes: Optional[str] = None


class EvidenceItem(BaseModel):
    id: str
    tlp: str
    domain: str
    summary: str
    raw_refs: list[Ref] = Field(default_factory=list)
    collected_at: str  # RFC3339
    related_entity_ids: Optional[list[str]] = None
    related_event_ids: Optional[list[str]] = None
    hash: Optional[str] = None


class Claim(BaseModel):
    id: str
    tlp: str
    statement: str
    polarity: str  # supports | contradicts | neutral
    confidence: float  # 0-1
    backed_by_evidence_ids: list[str] = Field(default_factory=list)
    subject_entity_ids: Optional[list[str]] = None
    time_range: Optional[TimeRange] = None
    derived_from_claim_ids: Optional[list[str]] = None
    assumption_ids: Optional[list[str]] = None


class Assumption(BaseModel):
    id: str
    tlp: str
    statement: str
    strength: str  # solid | caveated | unsupported
    rationale: str
    impacts: Optional[list[str]] = None


class Hypothesis(BaseModel):
    id: str
    tlp: str
    iq_id: str
    statement: str
    likelihood_score: float  # 0-1
    confidence_limit: float  # 0-1
    supporting_claim_ids: list[str] = Field(default_factory=list)
    contradicting_claim_ids: Optional[list[str]] = None
    gaps: list[str] = Field(default_factory=list)
    next_evidence_requests: list[dict] = Field(default_factory=list)
    status: Optional[str] = None  # open | ruled_in | ruled_out | stale
    updated_at: Optional[str] = None  # RFC3339


class InvestigationStep(BaseModel):
    stage: str
    description: str
    tool_calls: list[str] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)


class InvestigationReport(BaseModel):
    scenario_name: str
    investigation_question: str
    steps: list[InvestigationStep] = Field(default_factory=list)
    hypothesis: str
    likelihood_assessment: str
    confidence_assessment: str
    likelihood_score: float
    confidence_limit: float
    gaps: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    case_id: Optional[str] = None
    total_events_evaluated: int = 0
    tool_calls_used: int = 0
