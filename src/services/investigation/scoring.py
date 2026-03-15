"""Scoring functions for investigation hypothesis building.

Pure functions -- no I/O, no side effects. Extracted from demo_local.py
for reuse by the investigation pipeline and demo scripts.
"""
from src.types.core import (
    Claim, EvidenceItem, Hypothesis, Ref, TimeRange,
)
from src.utils.ulid import generate_ulid


def build_evidence_items(
    cred_events: list[dict],
    cov_envelope: dict,
    time_range: TimeRange,
) -> list[EvidenceItem]:
    """Wrap discovered events and coverage into EvidenceItem objects."""
    items = []

    for evt in cred_events:
        raw_refs = []
        for rr in evt.get("raw_refs", []):
            raw_refs.append(Ref(**rr))

        targets = evt.get("targets", [])
        related_entity_ids = [t["target_entity_id"] for t in targets]
        related_entity_ids.append(evt["actor"]["actor_entity_id"])

        items.append(EvidenceItem(
            id=generate_ulid(),
            tlp="AMBER",
            domain="identity",
            summary=f"{evt['action']} by {evt['actor']['actor_entity_id']} "
                    f"at {evt['ts']} (outcome={evt['outcome']})",
            raw_refs=raw_refs,
            collected_at=evt["ts"],
            related_entity_ids=related_entity_ids,
            related_event_ids=[evt["id"]],
        ))

    # Coverage as evidence
    cov = cov_envelope["coverage_report"]
    items.append(EvidenceItem(
        id=generate_ulid(),
        tlp="AMBER",
        domain="identity",
        summary=f"Coverage report: {cov['overall_status']} "
                f"({len(cov.get('sources', []))} source(s))",
        raw_refs=[],
        collected_at=time_range.end,
        related_entity_ids=[],
        related_event_ids=[],
    ))

    return items


def build_claims(
    cred_events: list[dict],
    source_ips: set[str],
    subject_id: str,
    evidence_items: list[EvidenceItem],
    cov_envelope: dict,
    time_range: TimeRange,
) -> list[Claim]:
    """Create Claim objects from correlation findings."""
    claims = []
    evidence_ids = [ei.id for ei in evidence_items]
    cov_status = cov_envelope["coverage_report"]["overall_status"]

    if cred_events:
        all_self_directed = all(
            evt["actor"]["actor_entity_id"] == subject_id
            for evt in cred_events
        )

        if all_self_directed:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"All {len(cred_events)} credential change(s) were "
                          f"self-directed by {subject_id}",
                polarity="supports",
                confidence=0.95 if cov_status == "complete" else 0.6,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[subject_id],
                time_range=time_range,
            ))

        single_ip = len(source_ips) <= 1
        if single_ip and source_ips:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"All activity from single source IP "
                          f"({', '.join(source_ips)})",
                polarity="supports",
                confidence=0.9 if cov_status == "complete" else 0.5,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[subject_id],
                time_range=time_range,
            ))
        elif len(source_ips) > 1:
            claims.append(Claim(
                id=generate_ulid(),
                tlp="AMBER",
                statement=f"Multiple source IPs observed ({len(source_ips)}): "
                          f"{', '.join(sorted(source_ips))}",
                polarity="contradicts",
                confidence=0.8,
                backed_by_evidence_ids=evidence_ids,
                subject_entity_ids=[subject_id],
                time_range=time_range,
            ))

    # Coverage claim
    if cov_status != "complete":
        claims.append(Claim(
            id=generate_ulid(),
            tlp="AMBER",
            statement=f"Coverage is {cov_status} -- findings are constrained "
                      f"by data gaps",
            polarity="neutral",
            confidence=1.0,
            backed_by_evidence_ids=[evidence_ids[-1]] if evidence_ids else [],
            time_range=time_range,
        ))

    return claims


def build_hypothesis(
    claims: list[Claim],
    cov_envelope: dict,
    investigation_question: str,
    cred_events: list[dict],
    evidence_prefixes: list[str],
) -> Hypothesis:
    """Create a Hypothesis with scores derived from coverage and claims."""
    cov = cov_envelope["coverage_report"]
    cov_status = cov["overall_status"]

    supporting = [c for c in claims if c.polarity == "supports"]
    contradicting = [c for c in claims if c.polarity == "contradicts"]

    # Likelihood from claim confidences
    if supporting:
        likelihood = sum(c.confidence for c in supporting) / len(supporting)
    elif cred_events:
        likelihood = 0.5
    else:
        likelihood = 0.3

    # Confidence limit from coverage
    if cov_status == "complete":
        confidence_limit = 0.95
    elif cov_status == "partial":
        confidence_limit = 0.6
    else:
        confidence_limit = 0.3

    # Contradicting claims reduce likelihood
    if contradicting:
        likelihood *= 0.7

    gaps = [cov["id"]] if cov_status != "complete" else []

    next_evidence_requests = []
    if cov_status != "complete":
        next_evidence_requests.append({
            "domain": "identity",
            "tool": "search_events",
            "params": {
                "actions": [f"{p}*" for p in evidence_prefixes],
            },
            "priority": "high",
        })

    return Hypothesis(
        id=generate_ulid(),
        tlp="AMBER",
        iq_id=investigation_question,
        statement="Credential changes are legitimate self-service activity",
        likelihood_score=round(likelihood, 3),
        confidence_limit=round(confidence_limit, 3),
        supporting_claim_ids=[c.id for c in supporting],
        contradicting_claim_ids=[c.id for c in contradicting] or None,
        gaps=gaps,
        next_evidence_requests=next_evidence_requests,
        status="open",
    )


def build_narrative(
    hypothesis: Hypothesis,
    claims: list[Claim],
    cov_envelope: dict,
) -> dict:
    """Build formulaic narrative text for mechanical mode.

    Returns dict with: hypothesis_text, likelihood_assessment,
    confidence_assessment, gaps, next_steps.
    """
    cov = cov_envelope["coverage_report"]
    cov_status = cov["overall_status"]

    supporting = [c for c in claims if c.polarity == "supports"]
    contradicting = [c for c in claims if c.polarity == "contradicts"]

    # Hypothesis text
    hypothesis_text = hypothesis.statement

    # Likelihood assessment
    if supporting and not contradicting:
        likelihood_assessment = (
            f"Evidence supports the hypothesis. "
            f"{len(supporting)} supporting claim(s) with average confidence "
            f"{sum(c.confidence for c in supporting) / len(supporting):.2f}."
        )
    elif supporting and contradicting:
        likelihood_assessment = (
            f"Mixed evidence. {len(supporting)} supporting and "
            f"{len(contradicting)} contradicting claim(s). "
            f"Likelihood reduced due to contradicting evidence."
        )
    else:
        likelihood_assessment = (
            "Insufficient evidence to strongly support or contradict the hypothesis."
        )

    # Confidence assessment
    if cov_status == "complete":
        confidence_assessment = (
            "Full telemetry coverage available. "
            "Confidence limit is high (0.95)."
        )
    elif cov_status == "partial":
        confidence_assessment = (
            f"Partial telemetry coverage. "
            f"Confidence limit capped at 0.6 due to data gaps. "
            f"Findings may be incomplete."
        )
    else:
        confidence_assessment = (
            f"Coverage is {cov_status}. "
            f"Confidence limit is low (0.3). "
            f"Cannot draw reliable conclusions from available data."
        )

    # Gaps
    gaps = []
    if cov_status != "complete":
        for src in cov.get("sources", []):
            if src["status"] != "complete":
                gap_msg = f"{src['source_name']}: {src['status']}"
                if src.get("notes"):
                    gap_msg += f" -- {src['notes']}"
                gaps.append(gap_msg)

    # Next steps
    next_steps = []
    if cov_status != "complete":
        next_steps.append("Obtain complete telemetry to raise confidence limit")
    if contradicting:
        next_steps.append("Investigate contradicting evidence (multiple source IPs)")
    if not next_steps:
        next_steps.append("Investigation complete with high confidence")

    return {
        "hypothesis_text": hypothesis_text,
        "likelihood_assessment": likelihood_assessment,
        "confidence_assessment": confidence_assessment,
        "gaps": gaps,
        "next_steps": next_steps,
    }
