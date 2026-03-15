"""Investigation pipeline: orchestrates identity + case MCP servers.

Core function run_investigation() launches both servers as subprocesses,
executes a bounded investigation loop, and returns an InvestigationReport.
"""
import logging
import tempfile
from pathlib import Path

from src.services.investigation.mcp_client import open_mcp_session, call_tool
from src.services.investigation.scoring import (
    build_evidence_items,
    build_claims,
    build_hypothesis,
    build_narrative,
)
from src.types.core import InvestigationReport, InvestigationStep, TimeRange
from src.utils.serialization import load_yaml


_PROJECT_ROOT = str(Path(__file__).parent.parent.parent.parent)


def _load_manifest(scenario_path: Path) -> dict:
    """Read manifest.yaml and return structured metadata."""
    manifest = load_yaml(scenario_path / "manifest.yaml")
    time_range = manifest.get("time_range", {})
    return {
        "scenario_name": manifest.get("scenario_name", scenario_path.name),
        "description": manifest.get("description", ""),
        "question": manifest.get("investigation_question", ""),
        "time_range": TimeRange(
            start=time_range.get("start", "2026-01-01T00:00:00Z"),
            end=time_range.get("end", "2026-01-31T23:59:59Z"),
        ),
        "variant": manifest.get("variant", "unknown"),
        "tags": manifest.get("tags", []),
        "domains": manifest.get("domains", []),
    }


def _error_report(scenario_name: str, question: str, message: str) -> InvestigationReport:
    """Return an error report when the pipeline cannot continue."""
    return InvestigationReport(
        scenario_name=scenario_name,
        investigation_question=question,
        steps=[InvestigationStep(
            stage="error",
            description=message,
        )],
        hypothesis="Unable to complete investigation",
        likelihood_assessment=message,
        confidence_assessment="No assessment possible",
        likelihood_score=0.0,
        confidence_limit=0.0,
    )


async def run_investigation(
    scenario_path: Path,
    logger: logging.Logger,
    investigation_question: str | None = None,
    time_range_start: str | None = None,
    time_range_end: str | None = None,
    principal_hint: str | None = None,
    max_tool_calls: int = 30,
    max_events: int = 2000,
    use_llm: bool = False,
    llm_model: str | None = None,
) -> InvestigationReport:
    """Run a bounded investigation against a scenario via MCP subprocesses.

    Args:
        scenario_path: Path to scenario directory (contains manifest.yaml).
        logger: Logger instance (must write to stderr, not stdout).
        investigation_question: Override manifest's investigation_question.
        time_range_start: Override manifest's time range start (RFC3339).
        time_range_end: Override manifest's time range end (RFC3339).
        principal_hint: Hint for principal search query.
        max_tool_calls: Budget for total MCP tool calls.
        max_events: Max events to request from search_events.
        use_llm: If True, use LLM for narrative (scores still mechanical).
        llm_model: Model identifier for LLM mode.

    Returns:
        InvestigationReport with hypothesis, scores, gaps, and steps.
    """
    manifest = _load_manifest(scenario_path)
    scenario_name = manifest["scenario_name"]

    # Resolve question and time range (manifest defaults, parameter overrides)
    question = investigation_question or manifest["question"]
    time_range = TimeRange(
        start=time_range_start or manifest["time_range"].start,
        end=time_range_end or manifest["time_range"].end,
    )

    steps: list[InvestigationStep] = []
    tool_call_count = 0
    total_events_evaluated = 0

    def _check_budget() -> bool:
        return tool_call_count < max_tool_calls

    tmp_dir = tempfile.mkdtemp(prefix="blindsight_inv_")

    identity_cmd = "python"
    identity_args = [
        f"{_PROJECT_ROOT}/src/servers/identity_mcp.py",
        str(scenario_path),
    ]
    case_cmd = "python"
    case_args = [
        f"{_PROJECT_ROOT}/src/servers/case_mcp.py",
        tmp_dir,
    ]

    async with (
        open_mcp_session(identity_cmd, identity_args, logger) as id_session,
        open_mcp_session(case_cmd, case_args, logger) as case_session,
    ):

        # -- Step 1: Create case --
        step1 = InvestigationStep(stage="Create case", description="Open investigation case")
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        case_result = await call_tool(case_session, "create_case_tool", {
            "title": manifest["description"],
            "tlp": "AMBER",
            "severity": "sev3",
            "tags": manifest["tags"],
        }, logger)
        tool_call_count += 1
        step1.tool_calls.append("create_case_tool")

        # Extract case_id -- fail closed if missing
        results = case_result.get("results", [])
        if not results or "id" not in results[0]:
            return _error_report(
                scenario_name, question,
                f"Failed to create case: {case_result.get('error', {}).get('message', 'unknown error')}",
            )
        case_id = results[0]["id"]
        step1.key_findings.append(f"Case created: {case_id}")
        steps.append(step1)

        # -- Step 2: Check coverage --
        step2 = InvestigationStep(stage="Check coverage", description="Assess data availability and gaps")
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        cov_envelope = await call_tool(id_session, "describe_coverage", {
            "time_range_start": time_range.start,
            "time_range_end": time_range.end,
        }, logger)
        tool_call_count += 1
        step2.tool_calls.append("describe_coverage")

        cov_report = cov_envelope.get("coverage_report", {})
        cov_status = cov_report.get("overall_status", "unknown")
        step2.key_findings.append(f"Coverage: {cov_status}")
        steps.append(step2)

        # Ingest coverage into case
        if _check_budget():
            await call_tool(case_session, "ingest_records", {
                "case_id": case_id,
                "domain_response": cov_envelope,
            }, logger)
            tool_call_count += 1

        # -- Step 3: Discover principals --
        step3 = InvestigationStep(stage="Discover principals", description="Find subject entities")
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        principal_envelope = await call_tool(id_session, "search_entities", {
            "query": principal_hint or "",
            "entity_types": ["principal"],
        }, logger)
        tool_call_count += 1
        step3.tool_calls.append("search_entities")

        principals = principal_envelope.get("entities", [])
        step3.key_findings.append(f"Found {len(principals)} principal(s)")
        steps.append(step3)

        if not principals:
            return InvestigationReport(
                scenario_name=scenario_name,
                investigation_question=question,
                steps=steps,
                hypothesis="No principals found -- cannot proceed",
                likelihood_assessment="No assessment possible",
                confidence_assessment="No assessment possible",
                likelihood_score=0.0,
                confidence_limit=0.0,
                case_id=case_id,
                tool_calls_used=tool_call_count,
            )

        subject = principals[0]
        subject_id = subject["id"]
        step3.key_findings.append(f"Subject: {subject.get('display_name', subject_id)}")

        # Ingest principals into case
        if _check_budget():
            await call_tool(case_session, "ingest_records", {
                "case_id": case_id,
                "domain_response": principal_envelope,
            }, logger)
            tool_call_count += 1

        # -- Step 4: Map relationships --
        step4 = InvestigationStep(stage="Map relationships", description="Traverse entity relationships")
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        neighbor_envelope = await call_tool(id_session, "get_neighbors", {
            "entity_id": subject_id,
        }, logger)
        tool_call_count += 1
        step4.tool_calls.append("get_neighbors")

        relationships = neighbor_envelope.get("relationships", [])
        entities = neighbor_envelope.get("entities", [])
        step4.key_findings.append(f"{len(relationships)} relationship(s), {len(entities)} related entity(ies)")
        steps.append(step4)

        if _check_budget():
            await call_tool(case_session, "ingest_records", {
                "case_id": case_id,
                "domain_response": neighbor_envelope,
            }, logger)
            tool_call_count += 1

        # -- Step 5: Discover action types --
        step5 = InvestigationStep(stage="Discover action types", description="Query domain capabilities")
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        domain_info = await call_tool(id_session, "describe_domain", {}, logger)
        tool_call_count += 1
        step5.tool_calls.append("describe_domain")

        capabilities = domain_info.get("capabilities", {})
        all_prefixes = capabilities.get("supported_actions_prefixes", [])
        evidence_prefixes = [p for p in all_prefixes if p != "auth."]
        step5.key_findings.append(f"Action prefixes: {all_prefixes}")
        steps.append(step5)

        # -- Step 6: Search for evidence (all events, filter client-side) --
        step6 = InvestigationStep(
            stage="Search for evidence",
            description="Fetch events and partition into evidence vs background",
        )
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        limit = min(max_events, 2000)
        events_envelope = await call_tool(id_session, "search_events", {
            "time_range_start": time_range.start,
            "time_range_end": time_range.end,
            "limit": limit,
        }, logger)
        tool_call_count += 1
        step6.tool_calls.append("search_events")

        all_events = events_envelope.get("events", [])
        total_events_evaluated = len(all_events)

        # Partition: auth.login is background, everything else is evidence
        cred_events = [e for e in all_events if e.get("action") != "auth.login"]
        background_events = [e for e in all_events if e.get("action") == "auth.login"]

        step6.key_findings.append(
            f"{len(all_events)} total event(s): "
            f"{len(cred_events)} evidence, {len(background_events)} background (auth.login)"
        )

        # Check for truncation
        gaps = []
        if events_envelope.get("next_page_token"):
            gap_msg = f"Event results truncated at {limit}; additional events may exist"
            gaps.append(gap_msg)
            step6.key_findings.append(gap_msg)

        steps.append(step6)

        if _check_budget():
            await call_tool(case_session, "ingest_records", {
                "case_id": case_id,
                "domain_response": events_envelope,
            }, logger)
            tool_call_count += 1

        # -- Step 7: Narrow timeline --
        step7 = InvestigationStep(stage="Build timeline", description="Narrow window around evidence events")

        if cred_events and _check_budget():
            sorted_events = sorted(cred_events, key=lambda e: e.get("ts", ""))
            first_ts = sorted_events[0]["ts"]
            last_ts = sorted_events[-1]["ts"]
            narrow_start = first_ts[:10] + "T00:00:00Z"
            last_day = int(last_ts[8:10])
            narrow_end = last_ts[:8] + f"{min(last_day + 2, 28):02d}T23:59:59Z"

            narrow_envelope = await call_tool(id_session, "search_events", {
                "time_range_start": narrow_start,
                "time_range_end": narrow_end,
            }, logger)
            tool_call_count += 1
            step7.tool_calls.append("search_events")

            if _check_budget():
                await call_tool(case_session, "ingest_records", {
                    "case_id": case_id,
                    "domain_response": narrow_envelope,
                }, logger)
                tool_call_count += 1

            # Get timeline from case store
            if _check_budget():
                timeline_result = await call_tool(case_session, "get_timeline_tool", {
                    "case_id": case_id,
                    "time_range_start": narrow_start,
                    "time_range_end": narrow_end,
                }, logger)
                tool_call_count += 1
                step7.tool_calls.append("get_timeline_tool")

                timeline_events = timeline_result.get("events", [])
                step7.key_findings.append(f"{len(timeline_events)} timeline event(s)")

        steps.append(step7)

        # -- Step 8: Correlate from case store --
        step8 = InvestigationStep(stage="Correlate", description="Query case store for correlations")
        source_ips: set[str] = set()

        if _check_budget():
            case_events_result = await call_tool(case_session, "query_events_tool", {
                "case_id": case_id,
                "actor_entity_id": subject_id,
            }, logger)
            tool_call_count += 1
            step8.tool_calls.append("query_events_tool")

            for evt in case_events_result.get("events", []):
                ctx = evt.get("context") or {}
                if ctx.get("source_ip"):
                    source_ips.add(ctx["source_ip"])
            step8.key_findings.append(f"Source IPs: {sorted(source_ips) or '(none)'}")

        if _check_budget():
            case_neighbors_result = await call_tool(case_session, "query_neighbors_tool", {
                "case_id": case_id,
                "entity_id": subject_id,
                "relationship_types": ["has_credential"],
            }, logger)
            tool_call_count += 1
            step8.tool_calls.append("query_neighbors_tool")

            creds = case_neighbors_result.get("entities", [])
            step8.key_findings.append(f"{len(creds)} credential(s) linked")

        steps.append(step8)

        # -- Step 9: Score --
        step9 = InvestigationStep(stage="Score", description="Build evidence items, claims, and hypothesis")

        evidence_items = build_evidence_items(cred_events, cov_envelope, time_range)
        claims = build_claims(
            cred_events, source_ips, subject_id,
            evidence_items, cov_envelope, time_range,
        )
        hyp = build_hypothesis(
            claims, cov_envelope, question,
            cred_events, evidence_prefixes,
        )

        step9.key_findings.append(f"Likelihood: {hyp.likelihood_score}")
        step9.key_findings.append(f"Confidence limit: {hyp.confidence_limit}")
        step9.key_findings.append(f"{len(claims)} claim(s), {len(evidence_items)} evidence item(s)")
        steps.append(step9)

        # -- Step 10: Narrative --
        if use_llm:
            narrative = await _llm_narrative(hyp, claims, cov_envelope, question, llm_model)
        else:
            narrative = build_narrative(hyp, claims, cov_envelope)

        # Merge coverage gaps with truncation gaps
        all_gaps = gaps + narrative.get("gaps", [])
        if hyp.gaps:
            for g in hyp.gaps:
                if g not in all_gaps:
                    all_gaps.append(g)

        return InvestigationReport(
            scenario_name=scenario_name,
            investigation_question=question,
            steps=steps,
            hypothesis=narrative["hypothesis_text"],
            likelihood_assessment=narrative["likelihood_assessment"],
            confidence_assessment=narrative["confidence_assessment"],
            likelihood_score=hyp.likelihood_score,
            confidence_limit=hyp.confidence_limit,
            gaps=all_gaps,
            next_steps=narrative.get("next_steps", []),
            case_id=case_id,
            total_events_evaluated=total_events_evaluated,
            tool_calls_used=tool_call_count,
        )


async def _llm_narrative(
    hypothesis,
    claims,
    cov_envelope: dict,
    question: str,
    model: str | None,
) -> dict:
    """Generate narrative text using an LLM. Scores are always mechanical.

    Lazy-imports pydantic-ai to avoid requiring it for mechanical mode.
    Falls back to mechanical narrative on import or API errors.
    """
    try:
        from pydantic import BaseModel as PydanticBaseModel
        from pydantic_ai import Agent

        class Narrative(PydanticBaseModel):
            hypothesis_text: str
            likelihood_assessment: str
            confidence_assessment: str
            gaps: list[str]
            next_steps: list[str]

        supporting = [c for c in claims if c.polarity == "supports"]
        contradicting = [c for c in claims if c.polarity == "contradicts"]
        cov_status = cov_envelope.get("coverage_report", {}).get("overall_status", "unknown")

        prompt = (
            f"You are a security analyst summarizing an investigation.\n\n"
            f"Investigation question: {question}\n\n"
            f"Hypothesis: {hypothesis.statement}\n"
            f"Likelihood score: {hypothesis.likelihood_score}\n"
            f"Confidence limit: {hypothesis.confidence_limit}\n\n"
            f"Supporting claims ({len(supporting)}):\n"
        )
        for c in supporting:
            prompt += f"  - {c.statement} (confidence={c.confidence})\n"
        if contradicting:
            prompt += f"\nContradicting claims ({len(contradicting)}):\n"
            for c in contradicting:
                prompt += f"  - {c.statement} (confidence={c.confidence})\n"
        prompt += f"\nCoverage status: {cov_status}\n"
        prompt += (
            "\nWrite a concise narrative with:\n"
            "- hypothesis_text: one-sentence hypothesis statement\n"
            "- likelihood_assessment: what the evidence suggests\n"
            "- confidence_assessment: what can/cannot be verified\n"
            "- gaps: list of data gaps\n"
            "- next_steps: recommended follow-ups\n"
        )

        agent = Agent(
            model=model or "anthropic:claude-sonnet-4-20250514",
            output_type=Narrative,
        )
        result = await agent.run(prompt)
        n = result.output
        return {
            "hypothesis_text": n.hypothesis_text,
            "likelihood_assessment": n.likelihood_assessment,
            "confidence_assessment": n.confidence_assessment,
            "gaps": n.gaps,
            "next_steps": n.next_steps,
        }
    except Exception:
        # Fall back to mechanical narrative
        return build_narrative(hypothesis, claims, cov_envelope)
