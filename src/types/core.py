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
