"""Report generation data types.

ReportFacts is the deterministic payload collected from the case store.
ReportProse holds optional LLM-generated narrative sections.
"""
from dataclasses import dataclass, field

from blindsight.types.core import ScoreBand, GapAssessment, TLPLevel


@dataclass(frozen=True)
class ReportImpact:
    """Computed impact from app-domain events."""
    affected_principals: list[str] = field(default_factory=list)
    affected_resources: list[str] = field(default_factory=list)
    app_actions_summary: list[dict] = field(default_factory=list)
    transaction_count: int = 0
    transaction_total: float | None = None


@dataclass(frozen=True)
class ReportFacts:
    """Deterministic facts payload for report rendering."""
    # Scope
    case_id: str
    scenario_name: str
    investigation_question: str
    time_range_start: str
    time_range_end: str
    domains_queried: list[str]

    # Hypothesis
    hypothesis_statement: str
    likelihood: ScoreBand
    confidence: ScoreBand
    likelihood_rationale: str
    confidence_rationale: str
    gap_assessments: list[GapAssessment]

    # Evidence
    supporting_claims: list[dict]
    contradicting_claims: list[dict]
    neutral_claims: list[dict]
    evidence_items: list[dict]

    # Timeline (chronological events)
    timeline_events: list[dict]

    # Entities
    focal_principals: list[str]
    focal_primary: str | None
    entities: list[dict]

    # Impact (computed from app events)
    impact: ReportImpact

    # Coverage
    coverage_reports: list[dict]

    # TLP
    report_tlp: TLPLevel

    # Reproducibility
    tool_call_history: list[dict]
    total_events_evaluated: int
    generated_at: str


@dataclass(frozen=True)
class ReportProse:
    """LLM-generated prose for human-readable report sections."""
    executive_summary: str
    key_findings_narrative: str
    hypothesis_explanation: str
    recommended_followup: str
