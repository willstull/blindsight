"""Incident report generation service.

Renders a NIST SP 800-61 Rev. 3 / CSF 2.0 aligned Markdown report from
deterministic case store facts, with optional LLM-generated prose for
human-readable sections.

Architecture:
  - Deterministic code owns structure, evidence selection, event ordering,
    totals, coverage, tool-call history, raw refs, and section membership.
  - LLM owns only grounded prose for the human-readable sections.
  - The report is reproducible from the saved case, not from in-memory
    pipeline state.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from blindsight.types.core import GapAssessment
from blindsight.types.report import ReportFacts, ReportImpact, ReportProse
from blindsight.utils.tlp import max_tlp


# Transaction actions used for impact computation
TRANSACTION_ACTIONS = frozenset({"app.invoice.create", "app.payment.create"})


def claim_strength(confidence: float) -> str:
    """Map numeric claim confidence to a categorical strength label for display."""
    if confidence >= 0.85:
        return "strong"
    if confidence >= 0.65:
        return "moderate"
    return "weak"


def compute_impact(timeline_events: list[dict], entities: list[dict]) -> ReportImpact:
    """Compute impact from app-domain events and entities.

    Only app.invoice.create and app.payment.create contribute to
    transaction counts and totals. Amounts come from event context.

    Affected principals and resources are classified using the entity list.
    Entity IDs not found in the entity list are classified by prefix
    convention (principal_ vs resource_).
    """
    # Build entity type lookup from the entity list
    entity_types: dict[str, str] = {}
    for ent in entities:
        entity_types[ent["id"]] = ent.get("entity_type", "")

    affected_principals: set[str] = set()
    affected_resources: set[str] = set()
    action_counts: dict[str, int] = {}
    transaction_count = 0
    transaction_total = 0.0
    has_amounts = False

    def _classify(entity_id: str) -> None:
        etype = entity_types.get(entity_id, "")
        if etype == "principal" or (not etype and entity_id.startswith("principal_")):
            affected_principals.add(entity_id)
        elif etype == "resource" or (not etype and entity_id.startswith("resource_")):
            affected_resources.add(entity_id)
        else:
            # Unknown type -- default to resource for targets
            affected_resources.add(entity_id)

    for event in timeline_events:
        domain = event.get("domain", "")
        if domain != "app":
            continue

        action = event.get("action", "")
        action_counts[action] = action_counts.get(action, 0) + 1

        # Actor is always a principal
        actor = event.get("actor") or {}
        if isinstance(actor, dict):
            actor_id = actor.get("actor_entity_id")
            if actor_id:
                affected_principals.add(actor_id)

        # Targets classified by entity type
        for target in event.get("targets") or []:
            if isinstance(target, dict):
                tid = target.get("target_entity_id")
                if tid:
                    _classify(tid)

        # Transactions
        if action in TRANSACTION_ACTIONS:
            transaction_count += 1
            ctx = event.get("context") or {}
            if isinstance(ctx, dict):
                amount = ctx.get("amount")
                if amount is not None:
                    try:
                        transaction_total += float(amount)
                        has_amounts = True
                    except (ValueError, TypeError):
                        pass

    # Also include principals from entity list
    for ent in entities:
        if ent.get("entity_type") == "principal":
            affected_principals.add(ent["id"])

    app_actions_summary = [
        {"action": action, "count": count}
        for action, count in sorted(action_counts.items())
    ]

    return ReportImpact(
        affected_principals=sorted(affected_principals),
        affected_resources=sorted(affected_resources),
        app_actions_summary=app_actions_summary,
        transaction_count=transaction_count,
        transaction_total=transaction_total if has_amounts else None,
    )


def build_report_facts(facts_payload: dict) -> ReportFacts:
    """Build ReportFacts from the get_report_facts payload.

    Parses the case store payload, computes derived impact from timeline
    events, and determines report TLP as the max of all included content.
    """
    case = facts_payload.get("case") or {}
    metadata = case.get("investigation_metadata") or {}
    hypotheses = facts_payload.get("hypotheses", [])
    claims = facts_payload.get("claims", [])
    evidence_items = facts_payload.get("evidence_items", [])
    timeline = facts_payload.get("timeline", [])
    entities = facts_payload.get("entities", [])
    coverage_reports = facts_payload.get("coverage_reports", [])
    tool_call_history = facts_payload.get("tool_call_history", [])

    # Extract hypothesis (take the first/most recent)
    hyp = hypotheses[0] if hypotheses else {}
    gap_assessments = []
    for ga in hyp.get("gap_assessments", []):
        if isinstance(ga, dict):
            gap_assessments.append(GapAssessment(**ga))
        else:
            gap_assessments.append(ga)

    # Partition claims by polarity
    supporting = [c for c in claims if c.get("polarity") == "supports"]
    contradicting = [c for c in claims if c.get("polarity") == "contradicts"]
    neutral = [c for c in claims if c.get("polarity") not in ("supports", "contradicts")]

    # Compute impact from timeline
    impact = compute_impact(timeline, entities)

    # Compute report TLP as max of all included content
    tlp_values: list[str | None] = [case.get("tlp")]
    tlp_values.extend(e.get("tlp") for e in timeline)
    tlp_values.extend(ei.get("tlp") for ei in evidence_items)
    tlp_values.extend(c.get("tlp") for c in claims)
    tlp_values.extend(h.get("tlp") for h in hypotheses)
    report_tlp = max_tlp(tlp_values)

    return ReportFacts(
        case_id=case.get("id", "unknown"),
        scenario_name=metadata.get("scenario_name", "unknown"),
        investigation_question=metadata.get("investigation_question", "unknown"),
        time_range_start=metadata.get("time_range_start", ""),
        time_range_end=metadata.get("time_range_end", ""),
        domains_queried=metadata.get("domains_queried", []),
        hypothesis_statement=hyp.get("statement", "No hypothesis available"),
        likelihood=hyp.get("likelihood", "low"),
        confidence=hyp.get("confidence", "low"),
        likelihood_rationale=metadata.get("likelihood_rationale", "No rationale available"),
        confidence_rationale=metadata.get("confidence_rationale", "No rationale available"),
        gap_assessments=gap_assessments,
        supporting_claims=supporting,
        contradicting_claims=contradicting,
        neutral_claims=neutral,
        evidence_items=evidence_items,
        timeline_events=timeline,
        focal_principals=metadata.get("focal_principals", []),
        focal_primary=metadata.get("focal_primary"),
        entities=entities,
        impact=impact,
        coverage_reports=coverage_reports,
        report_tlp=report_tlp,
        tool_call_history=tool_call_history,
        total_events_evaluated=metadata.get("total_events_evaluated", 0),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def render_report(facts: ReportFacts, prose: ReportProse | None = None) -> str:
    """Render a complete Markdown incident report from ReportFacts.

    All 9 sections are always present. If prose is provided, LLM-generated
    text is used for narrative sections. Otherwise, deterministic fallback
    text is used.
    """
    sections = [
        _render_executive_summary(facts, prose),
        _render_scope(facts),
        _render_key_findings(facts, prose),
        _render_timeline(facts),
        _render_evidence_assessment(facts),
        _render_hypothesis_assessment(facts, prose),
        _render_impact_and_exposure(facts),
        _render_recommended_followup(facts, prose),
        _render_reproducibility_appendix(facts),
    ]
    return "\n\n".join(sections) + "\n"


def build_report_prose_prompt(facts: ReportFacts) -> str:
    """Build the LLM prompt for generating report prose.

    Extracted for testability. The prompt includes the grounding contract
    and all facts needed for prose generation.
    """
    prompt = (
        "You are a security analyst writing sections of an incident report.\n\n"
        "## Grounding and wording rules\n"
        "- Use only the provided facts.\n"
        "- Do not invent facts, impact, root cause, business loss, "
        "exfiltration, fraud, or compromise paths.\n"
        "- Do not state that fraud, exfiltration, maliciousness, or an "
        "attack vector occurred unless those are explicit facts in the "
        "provided evidence.\n"
        "- Prefer cautious investigative wording: 'consistent with', "
        "'indicates', 'suggests', 'requires review', 'determine whether', "
        "'verify whether'.\n"
        "- When recommending follow-up actions, frame them as verification "
        "or review rather than asserting outcomes not established by "
        "the evidence.\n"
        "- Do not change likelihood, confidence, claim strength, TLP, "
        "event counts, transaction totals, or coverage status.\n"
        "- If a fact is not present, say it is not established.\n"
        "- Mention material gaps.\n"
        "- Reference claim strength as strong/moderate/weak (not numeric).\n\n"
        f"## Investigation question\n{facts.investigation_question}\n\n"
        f"## Hypothesis\n{facts.hypothesis_statement}\n"
        f"Likelihood: {facts.likelihood}\n"
        f"Confidence: {facts.confidence}\n\n"
    )

    # Claims (use categorical strength, not raw confidence)
    prompt += f"## Supporting claims ({len(facts.supporting_claims)})\n"
    for c in facts.supporting_claims[:10]:
        strength = claim_strength(c.get("confidence", 0))
        prompt += f"- {c.get('statement', '')} (claim strength: {strength})\n"
    if facts.contradicting_claims:
        prompt += f"\n## Contradicting claims ({len(facts.contradicting_claims)})\n"
        for c in facts.contradicting_claims[:10]:
            strength = claim_strength(c.get("confidence", 0))
            prompt += f"- {c.get('statement', '')} (claim strength: {strength})\n"

    # Gap assessments
    if facts.gap_assessments:
        prompt += "\n## Gap assessments\n"
        for ga in facts.gap_assessments:
            prompt += (
                f"- {ga.gap_id}: {ga.relevance} "
                f"(could_change={ga.could_change_conclusion}) -- {ga.reason}\n"
            )

    # Impact
    prompt += "\n## Impact\n"
    prompt += f"- Affected principals: {len(facts.impact.affected_principals)}\n"
    prompt += f"- Affected resources: {len(facts.impact.affected_resources)}\n"
    prompt += f"- Transaction count: {facts.impact.transaction_count}\n"
    if facts.impact.transaction_total is not None:
        prompt += f"- Transaction total: ${facts.impact.transaction_total:,.2f}\n"

    # Coverage
    prompt += f"\n## Coverage reports ({len(facts.coverage_reports)})\n"
    for cr in facts.coverage_reports:
        prompt += f"- {cr.get('domain', 'unknown')}: {cr.get('overall_status', 'unknown')}\n"

    prompt += (
        "\n## Sections to write\n"
        "Write four sections. Each must be grounded in the facts above.\n\n"
        "1. **executive_summary**: 2-3 sentence summary for stakeholders. "
        "Include scenario, key finding, likelihood, and confidence.\n"
        "2. **key_findings_narrative**: Narrative of what the investigation found. "
        "Reference specific claims and evidence.\n"
        "3. **hypothesis_explanation**: Explain the hypothesis assessment. "
        "Why this likelihood? Why this confidence? Reference gap assessments.\n"
        "4. **recommended_followup**: Specific follow-up actions based on gaps "
        "and findings. Be actionable. Format as a Markdown numbered list "
        "(one item per line, e.g. '1. Do X\\n2. Do Y'). "
        "Frame each action as verification or review, not as confirming "
        "a conclusion. The follow-up should determine what happened, not "
        "assert what happened.\n"
    )

    return prompt


async def generate_report_prose(
    facts: ReportFacts,
    model: str | None = None,
) -> ReportProse:
    """Generate report prose using an LLM.

    Falls back to deterministic prose on any failure.
    """
    try:
        from pydantic import BaseModel as PydanticBaseModel
        from pydantic_ai import Agent

        class ProseOutput(PydanticBaseModel):
            executive_summary: str
            key_findings_narrative: str
            hypothesis_explanation: str
            recommended_followup: str

        prompt = build_report_prose_prompt(facts)
        agent = Agent(
            model=model or "anthropic:claude-sonnet-4-20250514",
            output_type=ProseOutput,
        )
        result = await agent.run(prompt)
        output = result.output
        return ReportProse(
            executive_summary=output.executive_summary,
            key_findings_narrative=output.key_findings_narrative,
            hypothesis_explanation=output.hypothesis_explanation,
            recommended_followup=output.recommended_followup,
        )
    except Exception:
        return _fallback_prose(facts)


def _fallback_prose(facts: ReportFacts) -> ReportProse:
    """Deterministic prose fallback when LLM is unavailable.

    Generates scenario-specific text from the facts rather than
    generic boilerplate.
    """
    # Executive summary: mention key findings, impact, and domains
    exec_parts = [
        f"Investigation of {facts.scenario_name}: "
        f"{facts.investigation_question}",
    ]
    if facts.supporting_claims:
        top_claim = facts.supporting_claims[0].get("statement", "")
        if top_claim:
            exec_parts.append(f"Primary finding: {top_claim}.")
    if facts.impact.transaction_count > 0 and facts.impact.transaction_total is not None:
        exec_parts.append(
            f"The investigation identified {facts.impact.transaction_count} "
            f"financial transaction(s) totaling ${facts.impact.transaction_total:,.2f} "
            f"across the app domain."
        )
    exec_parts.append(
        f"Assessment: likelihood {facts.likelihood}, confidence {facts.confidence}."
    )

    # Key findings narrative: reference actual claims and domains
    findings_parts = []
    if facts.supporting_claims:
        findings_parts.append(
            f"{len(facts.supporting_claims)} supporting claim(s) identified"
        )
    if facts.contradicting_claims:
        findings_parts.append(
            f"{len(facts.contradicting_claims)} contradicting claim(s)"
        )
    findings_parts.append(
        f"{len(facts.evidence_items)} evidence item(s) collected "
        f"across {', '.join(facts.domains_queried) if facts.domains_queried else 'unknown'} domain(s)"
    )
    if facts.impact.app_actions_summary:
        action_summary = ", ".join(
            f"{a['action']} ({a['count']})"
            for a in facts.impact.app_actions_summary
        )
        findings_parts.append(f"App-domain activity: {action_summary}")

    # Recommended follow-up: scenario-specific based on actual state
    followup_parts = []
    if facts.gap_assessments:
        critical_gaps = [ga for ga in facts.gap_assessments if ga.relevance == "critical"]
        if critical_gaps:
            followup_parts.append(
                f"Address {len(critical_gaps)} critical coverage gap(s): "
                + ", ".join(ga.gap_id for ga in critical_gaps) + "."
            )
        relevant_gaps = [ga for ga in facts.gap_assessments if ga.relevance == "relevant"]
        if relevant_gaps:
            followup_parts.append(
                f"Investigate {len(relevant_gaps)} relevant gap(s) that may affect conclusion."
            )
    if not followup_parts:
        # No gaps -- focus on actionable next steps from the findings
        if facts.impact.transaction_count > 0:
            followup_parts.append(
                f"Review {facts.impact.transaction_count} flagged transaction(s) "
                f"for authorization and legitimacy."
            )
        if len(facts.impact.affected_principals) > 1:
            followup_parts.append(
                f"Audit credential and access state for "
                f"{len(facts.impact.affected_principals)} affected principal(s)."
            )
        followup_parts.append(
            "Correlate findings with additional telemetry sources not covered "
            "in this investigation."
        )
        followup_parts.append(
            "Determine organizational impact and initiate response procedures "
            "as warranted by the findings."
        )

    return ReportProse(
        executive_summary=" ".join(exec_parts),
        key_findings_narrative=". ".join(findings_parts) + ".",
        hypothesis_explanation=(
            f"{facts.likelihood_rationale} {facts.confidence_rationale}"
        ),
        recommended_followup="\n".join(f"- {p}" for p in followup_parts),
    )


# -- Section renderers --


def _render_executive_summary(facts: ReportFacts, prose: ReportProse | None) -> str:
    text = prose.executive_summary if prose else _fallback_prose(facts).executive_summary
    return (
        f"# Incident Report: {facts.scenario_name}\n\n"
        f"**TLP: {facts.report_tlp}**\n\n"
        f"## 1. Executive Summary\n\n{text}"
    )


def _render_scope(facts: ReportFacts) -> str:
    lines = [
        "## 2. Scope",
        "",
        f"- **Case ID**: {facts.case_id}",
        f"- **Scenario**: {facts.scenario_name}",
        f"- **Investigation question**: {facts.investigation_question}",
        f"- **Time range**: {facts.time_range_start} to {facts.time_range_end}",
        f"- **Domains queried**: {', '.join(facts.domains_queried) if facts.domains_queried else 'none'}",
        f"- **Focal principal(s)**: {', '.join(facts.focal_principals) if facts.focal_principals else 'none identified'}",
    ]
    if facts.focal_primary:
        lines.append(f"- **Primary focal**: {facts.focal_primary}")
    return "\n".join(lines)


def _render_key_findings(facts: ReportFacts, prose: ReportProse | None) -> str:
    text = prose.key_findings_narrative if prose else _fallback_prose(facts).key_findings_narrative
    lines = ["## 3. Key Findings", "", text, ""]

    if facts.supporting_claims:
        lines.append("### Supporting claims")
        lines.append("")
        for c in facts.supporting_claims:
            conf = c.get("confidence", 0)
            lines.append(
                f"- {c.get('statement', '')} "
                f"(claim strength: {claim_strength(conf)})"
            )
        lines.append("")

    if facts.contradicting_claims:
        lines.append("### Contradicting claims")
        lines.append("")
        for c in facts.contradicting_claims:
            conf = c.get("confidence", 0)
            lines.append(
                f"- {c.get('statement', '')} "
                f"(claim strength: {claim_strength(conf)})"
            )
        lines.append("")

    return "\n".join(lines)


def _render_timeline(facts: ReportFacts) -> str:
    lines = ["## 4. Timeline", ""]

    if not facts.timeline_events:
        lines.append("No events recorded.")
        return "\n".join(lines)

    lines.append("| Time | Domain | Action | Actor | Target | Outcome |")
    lines.append("|------|--------|--------|-------|--------|---------|")

    for event in facts.timeline_events:
        ts = event.get("ts", "")
        domain = event.get("domain", "")
        action = event.get("action", "")
        actor = event.get("actor") or {}
        actor_id = actor.get("actor_entity_id", "") if isinstance(actor, dict) else ""
        targets = event.get("targets") or []
        target_ids = []
        for t in targets:
            if isinstance(t, dict):
                tid = t.get("target_entity_id", "")
                if tid:
                    target_ids.append(tid)
        target_str = ", ".join(target_ids) if target_ids else ""
        outcome = event.get("outcome", "")
        lines.append(f"| {ts} | {domain} | {action} | {actor_id} | {target_str} | {outcome} |")

    return "\n".join(lines)


def _render_evidence_assessment(facts: ReportFacts) -> str:
    lines = ["## 5. Evidence Assessment", ""]

    lines.append(f"**Evidence items collected**: {len(facts.evidence_items)}")
    lines.append("")

    if facts.evidence_items:
        for ei in facts.evidence_items:
            summary = ei.get("summary", "")
            domain = ei.get("domain", "")
            lines.append(f"- [{domain}] {summary}")
        lines.append("")

    # Coverage assessment -- deduplicated by domain + source
    lines.append("### Coverage")
    lines.append("")
    if facts.coverage_reports:
        seen_domains: dict[str, str] = {}  # domain -> worst status
        seen_sources: dict[str, dict] = {}  # "domain:source_name" -> source dict
        status_rank = {"complete": 0, "unknown": 1, "partial": 2, "missing": 3}

        for cr in facts.coverage_reports:
            domain = cr.get("domain", "unknown")
            status = cr.get("overall_status", "unknown")
            if domain not in seen_domains or status_rank.get(status, 1) > status_rank.get(seen_domains[domain], 1):
                seen_domains[domain] = status
            for source in cr.get("sources", []):
                sname = source.get("source_name", "unknown")
                key = f"{domain}:{sname}"
                sstatus = source.get("status", "unknown")
                if key not in seen_sources or status_rank.get(sstatus, 1) > status_rank.get(seen_sources[key].get("status", ""), 1):
                    seen_sources[key] = {**source, "domain": domain}

        for domain in sorted(seen_domains):
            lines.append(f"- **{domain}**: {seen_domains[domain]}")
            for key, source in sorted(seen_sources.items()):
                if source["domain"] == domain:
                    sname = source.get("source_name", "unknown")
                    sstatus = source.get("status", "unknown")
                    lines.append(f"  - {sname}: {sstatus}")
                    if source.get("missing_fields"):
                        lines.append(f"    Missing: {', '.join(source['missing_fields'])}")
    else:
        lines.append("No coverage reports available.")

    return "\n".join(lines)


def _render_hypothesis_assessment(facts: ReportFacts, prose: ReportProse | None) -> str:
    text = prose.hypothesis_explanation if prose else _fallback_prose(facts).hypothesis_explanation
    lines = [
        "## 6. Hypothesis Assessment",
        "",
        f"**Hypothesis**: {facts.hypothesis_statement}",
        "",
        f"- **Likelihood**: {facts.likelihood}",
        f"- **Confidence**: {facts.confidence}",
        "",
        text,
    ]

    if facts.gap_assessments:
        lines.append("")
        lines.append("### Gap assessments")
        lines.append("")
        lines.append("| Gap | Relevance | Could change conclusion | Reason |")
        lines.append("|-----|-----------|----------------------|--------|")
        for ga in facts.gap_assessments:
            lines.append(
                f"| {ga.gap_id} | {ga.relevance} | "
                f"{'yes' if ga.could_change_conclusion else 'no'} | {ga.reason} |"
            )

    return "\n".join(lines)


def _render_impact_and_exposure(facts: ReportFacts) -> str:
    impact = facts.impact
    lines = ["## 7. Impact and Exposure", ""]

    lines.append(f"- **Affected principals**: {len(impact.affected_principals)}")
    if impact.affected_principals:
        for p in impact.affected_principals:
            lines.append(f"  - {p}")

    lines.append(f"- **Affected resources**: {len(impact.affected_resources)}")
    if impact.affected_resources:
        for r in impact.affected_resources:
            lines.append(f"  - {r}")

    if impact.app_actions_summary:
        lines.append("")
        lines.append("### App-domain actions")
        lines.append("")
        for entry in impact.app_actions_summary:
            lines.append(f"- {entry['action']}: {entry['count']}")

    lines.append("")
    lines.append(f"**Transaction count**: {impact.transaction_count}")
    if impact.transaction_total is not None:
        lines.append(f"**Transaction total**: ${impact.transaction_total:,.2f}")
    else:
        lines.append("**Transaction total**: not available from evidence")

    lines.append("")
    lines.append(
        "Impact figures are computed from observed app-domain events only. "
        "Actual business impact may differ."
    )

    return "\n".join(lines)


def _render_recommended_followup(facts: ReportFacts, prose: ReportProse | None) -> str:
    text = prose.recommended_followup if prose else _fallback_prose(facts).recommended_followup
    return f"## 8. Recommended Follow-Up\n\n{text}"


def _render_reproducibility_appendix(facts: ReportFacts) -> str:
    lines = [
        "## 9. Reproducibility Appendix",
        "",
        f"- **Case ID**: {facts.case_id}",
        f"- **Scenario**: {facts.scenario_name}",
        f"- **Investigation question**: {facts.investigation_question}",
        f"- **Domains queried**: {', '.join(facts.domains_queried) if facts.domains_queried else 'none'}",
        f"- **Total events evaluated**: {facts.total_events_evaluated}",
        f"- **Report generated**: {facts.generated_at}",
        f"- **TLP**: {facts.report_tlp}",
    ]

    # Coverage report IDs
    if facts.coverage_reports:
        lines.append("")
        lines.append("### Coverage report IDs")
        lines.append("")
        for cr in facts.coverage_reports:
            lines.append(f"- {cr.get('id', 'unknown')} ({cr.get('domain', '')})")

    # Evidence item IDs
    if facts.evidence_items:
        lines.append("")
        lines.append("### Evidence IDs")
        lines.append("")
        for ei in facts.evidence_items:
            lines.append(f"- {ei.get('id', 'unknown')}")

    # Tool call history
    if facts.tool_call_history:
        lines.append("")
        lines.append("### Tool call history")
        lines.append("")
        lines.append("| Tool | Domain | Status | Executed at |")
        lines.append("|------|--------|--------|-------------|")
        for tc in facts.tool_call_history:
            lines.append(
                f"| {tc.get('tool_name', '')} | {tc.get('domain', '')} | "
                f"{tc.get('response_status', '')} | {tc.get('executed_at', '')} |"
            )

    return "\n".join(lines)


async def generate_report_for_case(
    cases_dir: Path,
    case_id: str,
    logger: logging.Logger,
    use_llm: bool = False,
    llm_model: str | None = None,
) -> str:
    """Generate a Markdown incident report for a saved case.

    Reads facts directly from the case DuckDB file (no MCP subprocess
    roundtrip), assembles ReportFacts, optionally renders LLM prose, and
    returns the rendered Markdown.

    Raises FileNotFoundError if no DB exists for case_id, and propagates
    Result errors from the case store as exceptions for CLI surfacing.
    """
    from blindsight.services.case.query import get_report_facts
    from blindsight.services.case.store import open_case_db

    db_path = cases_dir / f"{case_id}.duckdb"
    if not db_path.exists():
        raise FileNotFoundError(f"No case DB found for '{case_id}' at {db_path}")

    conn_result = open_case_db(logger, db_path)
    if conn_result.is_err():
        raise conn_result.err()
    conn = conn_result.ok()
    try:
        facts_result = get_report_facts(logger, conn, case_id)
        if facts_result.is_err():
            raise facts_result.err()
        facts = build_report_facts(facts_result.ok())
    finally:
        conn.close()

    prose = None
    if use_llm:
        prose = await generate_report_prose(facts, model=llm_model)

    return render_report(facts, prose)
