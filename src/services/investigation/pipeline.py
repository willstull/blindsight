"""Investigation pipeline: orchestrates domain + case MCP servers.

Core function run_investigation() launches domain servers (identity, optionally app)
and a case server as subprocesses, executes a bounded investigation loop, and
returns an InvestigationReport.
"""
import logging
import tempfile
import time
from contextlib import AsyncExitStack
from pathlib import Path

from src.services.investigation.aggregation import aggregate_evidence
from src.services.investigation.focal import resolve_focal_principals
from src.services.investigation.mcp_client import open_mcp_session, call_tool
from src.services.investigation.scoring import (
    build_evidence_items,
    build_claims,
    build_hypothesis,
    build_narrative,
    extract_coverage_gaps,
    fallback_gap_assessments,
    score_and_classify,
    score_confidence_from_gaps,
    NarrativeResult,
)
from src.types.core import (
    CoverageObservation, GapAssessment,
    InvestigationReport, InvestigationStep, TimeRange,
)
from src.utils.serialization import load_yaml


_PROJECT_ROOT = str(Path(__file__).parent.parent.parent.parent)


async def _call_and_record(
    session,
    case_session,
    tool_name: str,
    arguments: dict,
    logger: logging.Logger,
    case_id: str,
    domain: str,
) -> dict:
    """Call a tool and record the call in the case store for audit history.

    Returns the tool response dict. Recording failures are logged but
    do not block the pipeline.
    """
    start = time.monotonic()
    result = await call_tool(session, tool_name, arguments, logger)
    duration_ms = int((time.monotonic() - start) * 1000)

    # Record the tool call -- best-effort, don't fail the pipeline
    try:
        await call_tool(case_session, "record_tool_call_tool", {
            "case_id": case_id,
            "domain": domain,
            "tool_name": tool_name,
            "request_params": arguments,
            "response_status": result.get("status", "unknown"),
            "response_body": result,
            "duration_ms": duration_ms,
        }, logger)
    except Exception:
        logger.warning("Failed to record tool call", extra={"tool": tool_name})

    return result


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
        likelihood_rationale=message,
        confidence_rationale="No assessment possible",
        likelihood="low",
        confidence="low",
    )


def _coverage_observations_from_response(
    stage: str,
    tool_name: str,
    response: dict,
) -> list[CoverageObservation]:
    """Extract coverage observations from an MCP tool response.

    Inspects the response envelope for coverage signals. Returns
    CoverageObservation objects for each signal found.

    empty_result observations are contextual -- they do NOT automatically
    become confidence-reducing gaps. Only coverage_gap, missing_fields,
    and limitation types feed into gap assessment.
    """
    observations: list[CoverageObservation] = []

    # Check coverage report sources for gaps
    cov_report = response.get("coverage_report", {})
    for source in cov_report.get("sources", []):
        if source.get("status") in ("partial", "missing"):
            observations.append(CoverageObservation(
                tool_name=tool_name,
                stage=stage,
                observation_type="coverage_gap",
                description=source.get("notes", f"{source['source_name']} is {source['status']}"),
            ))
        if source.get("missing_fields"):
            observations.append(CoverageObservation(
                tool_name=tool_name,
                stage=stage,
                observation_type="missing_fields",
                description=f"Missing fields from {source['source_name']}: {', '.join(source['missing_fields'])}",
            ))

    # Check for limitations
    for lim in response.get("limitations", []):
        lim_text = lim if isinstance(lim, str) else str(lim)
        observations.append(CoverageObservation(
            tool_name=tool_name,
            stage=stage,
            observation_type="limitation",
            description=lim_text,
        ))

    # Check for empty results (context, not automatic gap)
    for key in ("entities", "events", "relationships"):
        items = response.get(key)
        if items is not None and len(items) == 0:
            observations.append(CoverageObservation(
                tool_name=tool_name,
                stage=stage,
                observation_type="empty_result",
                description=f"{tool_name} returned 0 {key}",
                result_count=0,
            ))

    return observations


def _build_gap_assessment_prompt(
    hypothesis_statement: str,
    scored_claims: list,
    coverage_gaps: list[dict],
    observations: list[CoverageObservation],
) -> str:
    """Build the LLM prompt for gap relevance classification.

    Extracted for testability. The prompt contract includes:
    - Hypothesis statement
    - Supporting and contradicting claims with confidence
    - Coverage gaps to classify
    - Broader observations for context
    - Allowed relevance values and could_change_conclusion definition
    - Instructions to classify only provided gaps and not invent evidence
    """
    supporting = [c for c in scored_claims if c.polarity == "supports"]
    contradicting = [c for c in scored_claims if c.polarity == "contradicts"]

    prompt = (
        "You are a security analyst assessing whether coverage gaps in an "
        "investigation could affect the conclusion.\n\n"
        f"## Hypothesis\n{hypothesis_statement}\n\n"
        f"## Supporting claims ({len(supporting)})\n"
    )
    for c in supporting[:10]:  # cap to keep prompt compact
        prompt += f"- {c.statement} (confidence={c.confidence})\n"

    if contradicting:
        prompt += f"\n## Contradicting claims ({len(contradicting)})\n"
        for c in contradicting[:10]:
            prompt += f"- {c.statement} (confidence={c.confidence})\n"

    prompt += "\n## Coverage gaps to classify\n"
    for gap in coverage_gaps:
        prompt += (
            f"- gap_id: {gap['gap_id']}\n"
            f"  source: {gap.get('source_name', 'unknown')}\n"
            f"  status: {gap.get('status', 'unknown')}\n"
            f"  description: {gap.get('description', '')}\n"
        )

    # Include broader observations as context (capped)
    if observations:
        prompt += "\n## Investigation observations (context)\n"
        for obs in observations[:20]:
            prompt += f"- [{obs.observation_type}] {obs.stage}/{obs.tool_name}: {obs.description}\n"

    prompt += (
        "\n## Instructions\n"
        "For each coverage gap listed above, classify its relevance to "
        "the hypothesis.\n\n"
        "Allowed relevance values: critical, relevant, minor, irrelevant\n\n"
        "For could_change_conclusion:\n"
        "- true = if this missing evidence were available, it could "
        "reasonably support a different hypothesis or materially weaken "
        "the current one\n"
        "- false = it would improve detail or confidence, but is unlikely "
        "to alter the main conclusion\n\n"
        "Classify ONLY the gaps listed above. Do NOT invent new gaps. "
        "Do NOT invent evidence. Base your assessment on what the "
        "investigation actually found and what is missing.\n\n"
        "Return a JSON object with an 'assessments' array. Each element "
        "must have: gap_id, relevance, could_change_conclusion, reason."
    )

    return prompt


def _dedup_by_id(items: list[dict]) -> list[dict]:
    """Deduplicate dicts by their 'id' field, preserving order."""
    seen: set[str] = set()
    result = []
    for item in items:
        item_id = item.get("id", "")
        if item_id and item_id in seen:
            continue
        seen.add(item_id)
        result.append(item)
    return result


_STATUS_RANK = {"complete": 0, "unknown": 1, "partial": 2, "missing": 3}


def _merge_coverage_envelopes(*envelopes: dict) -> dict:
    """Merge coverage reports from multiple domain envelopes.

    Combines sources with domain-prefixed names. Takes worst overall_status.
    Returns a composite envelope for scoring/gap extraction.
    """
    reports = [
        e.get("coverage_report")
        for e in envelopes
        if e and e.get("coverage_report")
    ]
    if not reports:
        return {}

    merged = dict(reports[0])
    merged["domain"] = "multi"
    merged["sources"] = []
    worst = "complete"
    notes = []

    for report in reports:
        domain = report.get("domain", "unknown")
        status = report.get("overall_status", "unknown")
        if _STATUS_RANK.get(status, 1) > _STATUS_RANK.get(worst, 1):
            worst = status
        if report.get("notes"):
            notes.append(f"{domain}: {report['notes']}")
        for source in report.get("sources", []):
            enriched = dict(source)
            enriched["domain"] = domain
            enriched["source_name"] = f"{domain}:{source.get('source_name', 'unknown')}"
            merged["sources"].append(enriched)

    merged["overall_status"] = worst
    merged["notes"] = "; ".join(notes) if notes else None
    return {"coverage_report": merged}


async def run_investigation(
    scenario_path: Path,
    logger: logging.Logger,
    investigation_question: str | None = None,
    time_range_start: str | None = None,
    time_range_end: str | None = None,
    principal_hint: str | None = None,
    max_tool_calls: int = 40,
    max_events: int = 2000,
    use_llm: bool = True,
    llm_model: str | None = None,
    cases_dir: str | None = None,
    tlp: str = "AMBER",
    severity: str = "sev3",
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
        use_llm: If True, use LLM for gap assessment and narrative.
        llm_model: Model identifier for LLM mode.
        cases_dir: Directory for case DB files. If None, uses a temp directory.
        tlp: TLP marking for the case (default AMBER).
        severity: Severity level for the case (default sev3).

    Returns:
        InvestigationReport with hypothesis, gaps, and steps.
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
    coverage_observations: list[CoverageObservation] = []

    def _check_budget() -> bool:
        return tool_call_count < max_tool_calls

    tmp_dir = cases_dir or tempfile.mkdtemp(prefix="blindsight_inv_")
    has_app_domain = "app" in manifest.get("domains", [])

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
    app_cmd = "python"
    app_args = [
        f"{_PROJECT_ROOT}/src/servers/app_mcp.py",
        str(scenario_path),
    ]

    async with AsyncExitStack() as stack:
        id_session = await stack.enter_async_context(
            open_mcp_session(identity_cmd, identity_args, logger)
        )
        case_session = await stack.enter_async_context(
            open_mcp_session(case_cmd, case_args, logger)
        )
        app_session = None
        if has_app_domain:
            app_session = await stack.enter_async_context(
                open_mcp_session(app_cmd, app_args, logger)
            )

        # -- Step 1: Create case --
        step1 = InvestigationStep(stage="Create case", description="Open investigation case")
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        case_result = await call_tool(case_session, "create_case_tool", {
            "title": manifest["description"],
            "tlp": tlp,
            "severity": severity,
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

        # Record create_case_tool now that we have case_id
        try:
            await call_tool(case_session, "record_tool_call_tool", {
                "case_id": case_id,
                "domain": "case",
                "tool_name": "create_case_tool",
                "request_params": {
                    "title": manifest["description"],
                    "tlp": tlp,
                    "severity": severity,
                    "tags": manifest["tags"],
                },
                "response_status": case_result.get("status", "unknown"),
                "response_body": case_result,
            }, logger)
        except Exception:
            logger.warning("Failed to record create_case_tool call")

        # -- Step 2: Check coverage --
        step2 = InvestigationStep(stage="Check coverage", description="Assess data availability and gaps")
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        cov_envelope = await _call_and_record(
            id_session, case_session, "describe_coverage", {
                "time_range_start": time_range.start,
                "time_range_end": time_range.end,
            }, logger, case_id, "identity",
        )
        tool_call_count += 1
        step2.tool_calls.append("describe_coverage")

        cov_report = cov_envelope.get("coverage_report", {})
        cov_status = cov_report.get("overall_status", "unknown")
        step2.key_findings.append(f"Coverage: {cov_status}")
        coverage_observations.extend(
            _coverage_observations_from_response("Check coverage", "describe_coverage", cov_envelope)
        )
        steps.append(step2)

        # Ingest identity coverage into case
        if _check_budget():
            await call_tool(case_session, "ingest_records", {
                "case_id": case_id,
                "domain_response": cov_envelope,
            }, logger)
            tool_call_count += 1

        # App domain coverage (if available)
        app_cov_envelope = {}
        if app_session and _check_budget():
            app_cov_envelope = await _call_and_record(
                app_session, case_session, "describe_coverage", {
                    "time_range_start": time_range.start,
                    "time_range_end": time_range.end,
                }, logger, case_id, "app",
            )
            tool_call_count += 1
            step2.tool_calls.append("describe_coverage (app)")
            app_cov_status = app_cov_envelope.get("coverage_report", {}).get("overall_status", "unknown")
            step2.key_findings.append(f"App coverage: {app_cov_status}")
            coverage_observations.extend(
                _coverage_observations_from_response("Check coverage", "describe_coverage (app)", app_cov_envelope)
            )
            # Ingest app coverage into case
            if _check_budget():
                await call_tool(case_session, "ingest_records", {
                    "case_id": case_id,
                    "domain_response": app_cov_envelope,
                }, logger)
                tool_call_count += 1

        # Merge coverage envelopes for scoring (composite, worst-status wins)
        if app_cov_envelope:
            merged_cov_envelope = _merge_coverage_envelopes(cov_envelope, app_cov_envelope)
        else:
            merged_cov_envelope = cov_envelope

        # -- Step 3: Discover principals --
        step3 = InvestigationStep(stage="Discover principals", description="Find subject entities")
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        principal_envelope = await _call_and_record(
            id_session, case_session, "search_entities", {
                "query": principal_hint or "",
                "entity_types": ["principal"],
            }, logger, case_id, "identity",
        )
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
                likelihood_rationale="No assessment possible",
                confidence_rationale="No assessment possible",
                likelihood="low",
                confidence="low",
                case_id=case_id,
                tool_calls_used=tool_call_count,
            )

        # Ingest principals into case
        if _check_budget():
            await call_tool(case_session, "ingest_records", {
                "case_id": case_id,
                "domain_response": principal_envelope,
            }, logger)
            tool_call_count += 1

        # -- Step 4: Map relationships for ALL principals --
        step4 = InvestigationStep(
            stage="Map relationships",
            description="Traverse entity relationships for all principals",
        )
        all_relationships: list[dict] = []
        all_neighbor_entities: list[dict] = []

        for principal in principals:
            if not _check_budget():
                break

            neighbor_envelope = await _call_and_record(
                id_session, case_session, "get_neighbors", {
                    "entity_id": principal["id"],
                }, logger, case_id, "identity",
            )
            tool_call_count += 1
            step4.tool_calls.append("get_neighbors")

            all_relationships.extend(neighbor_envelope.get("relationships", []))
            all_neighbor_entities.extend(neighbor_envelope.get("entities", []))

            if _check_budget():
                await call_tool(case_session, "ingest_records", {
                    "case_id": case_id,
                    "domain_response": neighbor_envelope,
                }, logger)
                tool_call_count += 1

        # Deduplicate
        all_relationships = _dedup_by_id(all_relationships)
        all_neighbor_entities = _dedup_by_id(all_neighbor_entities)

        step4.key_findings.append(
            f"{len(all_relationships)} relationship(s), "
            f"{len(all_neighbor_entities)} related entity(ies)"
        )
        steps.append(step4)

        # -- Step 5: Discover action types --
        step5 = InvestigationStep(stage="Discover action types", description="Query domain capabilities")
        if not _check_budget():
            return _error_report(scenario_name, question, "Tool call budget exhausted")

        domain_info = await _call_and_record(
            id_session, case_session, "describe_domain", {},
            logger, case_id, "identity",
        )
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
        events_envelope = await _call_and_record(
            id_session, case_session, "search_events", {
                "time_range_start": time_range.start,
                "time_range_end": time_range.end,
                "limit": limit,
            }, logger, case_id, "identity",
        )
        tool_call_count += 1
        step6.tool_calls.append("search_events")

        all_events = events_envelope.get("events", [])
        total_events_evaluated = len(all_events)
        coverage_observations.extend(
            _coverage_observations_from_response("Search for evidence", "search_events", events_envelope)
        )

        # Partition: auth.login is background, everything else is evidence
        evidence_events = [e for e in all_events if e.get("action") != "auth.login"]
        background_events = [e for e in all_events if e.get("action") == "auth.login"]

        step6.key_findings.append(
            f"{len(all_events)} total event(s): "
            f"{len(evidence_events)} evidence, {len(background_events)} background (auth.login)"
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

        # App domain events (if available)
        if app_session and _check_budget():
            app_events_envelope = await _call_and_record(
                app_session, case_session, "search_events", {
                    "time_range_start": time_range.start,
                    "time_range_end": time_range.end,
                    "limit": limit,
                }, logger, case_id, "app",
            )
            tool_call_count += 1
            step6.tool_calls.append("search_events (app)")
            coverage_observations.extend(
                _coverage_observations_from_response("Search for evidence", "search_events (app)", app_events_envelope)
            )

            app_events = app_events_envelope.get("events", [])
            # All app events are evidence (no background partition)
            all_events = all_events + app_events
            evidence_events = evidence_events + app_events
            total_events_evaluated = len(all_events)

            step6.key_findings.append(
                f"{len(app_events)} app event(s) added to evidence pool"
            )

            # Ingest app events into case
            if _check_budget():
                await call_tool(case_session, "ingest_records", {
                    "case_id": case_id,
                    "domain_response": app_events_envelope,
                }, logger)
                tool_call_count += 1

        # -- Focal resolution --
        focal = resolve_focal_principals(
            question, principal_hint, principals, evidence_events, all_relationships,
        )
        focal_ids = focal.focal_ids

        # -- Step 7: Narrow timeline --
        step7 = InvestigationStep(stage="Build timeline", description="Narrow window around evidence events")

        if evidence_events and _check_budget():
            sorted_events = sorted(evidence_events, key=lambda e: e.get("ts", ""))
            first_ts = sorted_events[0]["ts"]
            last_ts = sorted_events[-1]["ts"]
            narrow_start = first_ts[:10] + "T00:00:00Z"
            last_day = int(last_ts[8:10])
            narrow_end = last_ts[:8] + f"{min(last_day + 2, 28):02d}T23:59:59Z"

            narrow_envelope = await _call_and_record(
                id_session, case_session, "search_events", {
                    "time_range_start": narrow_start,
                    "time_range_end": narrow_end,
                }, logger, case_id, "identity",
            )
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
                timeline_result = await _call_and_record(
                    case_session, case_session, "get_timeline_tool", {
                        "case_id": case_id,
                        "time_range_start": narrow_start,
                        "time_range_end": narrow_end,
                    }, logger, case_id, "case",
                )
                tool_call_count += 1
                step7.tool_calls.append("get_timeline_tool")

                timeline_events = timeline_result.get("events", [])
                step7.key_findings.append(f"{len(timeline_events)} timeline event(s)")

        steps.append(step7)

        # -- Step 8: Correlate from case store (iterate focal principals) --
        step8 = InvestigationStep(stage="Correlate", description="Query case store for correlations")

        for fid in focal_ids:
            if _check_budget():
                case_events_result = await _call_and_record(
                    case_session, case_session, "query_events_tool", {
                        "case_id": case_id,
                        "actor_entity_id": fid,
                    }, logger, case_id, "case",
                )
                tool_call_count += 1
                step8.tool_calls.append("query_events_tool")

                source_ips: set[str] = set()
                for evt in case_events_result.get("events", []):
                    ctx = evt.get("context") or {}
                    if ctx.get("source_ip"):
                        source_ips.add(ctx["source_ip"])
                if source_ips:
                    step8.key_findings.append(
                        f"Source IPs for {fid}: {sorted(source_ips)}"
                    )

            if _check_budget():
                case_neighbors_result = await _call_and_record(
                    case_session, case_session, "query_neighbors_tool", {
                        "case_id": case_id,
                        "entity_id": fid,
                        "relationship_types": ["has_credential"],
                    }, logger, case_id, "case",
                )
                tool_call_count += 1
                step8.tool_calls.append("query_neighbors_tool")

                creds = case_neighbors_result.get("entities", [])
                if creds:
                    step8.key_findings.append(
                        f"{len(creds)} credential(s) linked to {fid}"
                    )

        steps.append(step8)

        # -- Step 9: Score --
        step9 = InvestigationStep(stage="Score", description="Build evidence items, claims, and score likelihood")

        evidence_items = build_evidence_items(evidence_events, merged_cov_envelope, time_range, tlp=tlp)

        # Aggregate evidence before claim building
        aggregated_facts = aggregate_evidence(
            evidence_events, all_events, all_relationships, focal_ids,
        )

        claims = build_claims(
            evidence_events, all_events, focal,
            evidence_items, merged_cov_envelope, time_range, all_relationships,
            aggregated_facts=aggregated_facts, tlp=tlp,
        )
        scoring_result = score_and_classify(
            claims, evidence_events, question,
        )

        step9.key_findings.append(f"Likelihood: {scoring_result.likelihood}")
        step9.key_findings.append(f"{len(scoring_result.scored_claims)} claim(s), {len(evidence_items)} evidence item(s)")
        step9.key_findings.append(f"Focal principals: {focal_ids}")
        if focal.primary_id:
            step9.key_findings.append(f"Primary focal: {focal.primary_id}")
        if aggregated_facts:
            step9.key_findings.append(
                f"{len(aggregated_facts)} aggregated fact(s): "
                f"{', '.join(f.fact_type for f in aggregated_facts)}"
            )
        steps.append(step9)

        # -- Step 9.5: Assess coverage gap relevance --
        step9b = InvestigationStep(
            stage="Assess gaps",
            description="Classify coverage gap relevance for confidence",
        )

        coverage_gaps = extract_coverage_gaps(merged_cov_envelope, coverage_observations)

        if coverage_gaps and use_llm:
            gap_assessments = await _assess_gap_relevance(
                hypothesis=scoring_result.statement,
                scored_claims=scoring_result.scored_claims,
                gaps=coverage_gaps,
                observations=coverage_observations,
                model=llm_model,
            )
        elif coverage_gaps:
            gap_assessments = fallback_gap_assessments(coverage_gaps)
        else:
            gap_assessments = []

        confidence = score_confidence_from_gaps(gap_assessments)

        # Construct final hypothesis (all fields populated)
        hyp = build_hypothesis(
            scoring_result=scoring_result,
            confidence=confidence,
            gap_assessments=gap_assessments,
            investigation_question=question,
            tlp=tlp,
        )

        step9b.key_findings.append(f"Confidence: {confidence}")
        step9b.key_findings.append(f"{len(coverage_gaps)} coverage gap(s), {len(gap_assessments)} assessment(s)")
        if gap_assessments:
            for ga in gap_assessments:
                step9b.key_findings.append(
                    f"  {ga.gap_id}: {ga.relevance} (could_change={ga.could_change_conclusion})"
                )
        steps.append(step9b)

        # -- Step 10: Narrative --
        # Use scored_claims (with polarity assigned) so narrative and LLM
        # prompts see the correct supports/contradicts polarities.
        if use_llm:
            narrative = await _llm_narrative(hyp, scoring_result.scored_claims, merged_cov_envelope, question, llm_model)
        else:
            narrative = build_narrative(hyp, scoring_result.scored_claims, merged_cov_envelope)

        # -- Step 11: Persist analysis artifacts --
        # NOT gated by _check_budget() -- bookkeeping that must always happen.
        try:
            await call_tool(case_session, "ingest_records", {
                "case_id": case_id,
                "domain_response": {
                    "evidence_items": [ei.model_dump() for ei in evidence_items],
                    "claims": [c.model_dump() for c in scoring_result.scored_claims],
                    "hypotheses": [hyp.model_dump()],
                    "case_metadata": {
                        "scenario_name": scenario_name,
                        "investigation_question": question,
                        "time_range_start": time_range.start,
                        "time_range_end": time_range.end,
                        "focal_principals": focal_ids,
                        "focal_primary": focal.primary_id,
                        "domains_queried": manifest.get("domains", []),
                        "likelihood_rationale": narrative.likelihood_rationale,
                        "confidence_rationale": narrative.confidence_rationale,
                        "total_events_evaluated": total_events_evaluated,
                    },
                },
            }, logger)
            tool_call_count += 1
        except Exception:
            logger.warning("Failed to persist analysis artifacts to case store")

        # Merge coverage gaps with truncation gaps
        all_gaps = gaps + narrative.gaps
        if hyp.gaps:
            for g in hyp.gaps:
                if g not in all_gaps:
                    all_gaps.append(g)

        return InvestigationReport(
            scenario_name=scenario_name,
            investigation_question=question,
            steps=steps,
            hypothesis=narrative.hypothesis_text,
            likelihood_rationale=narrative.likelihood_rationale,
            confidence_rationale=narrative.confidence_rationale,
            likelihood=hyp.likelihood,
            confidence=hyp.confidence,
            gap_assessments=hyp.gap_assessments,
            gaps=all_gaps,
            next_steps=narrative.next_steps,
            case_id=case_id,
            total_events_evaluated=total_events_evaluated,
            tool_calls_used=tool_call_count,
            focal_principals=focal_ids,
            focal_primary=focal.primary_id,
        )


async def _assess_gap_relevance(
    hypothesis: str,
    scored_claims: list,
    gaps: list[dict],
    observations: list[CoverageObservation],
    model: str | None,
) -> list[GapAssessment]:
    """Classify coverage gap relevance using an LLM.

    Falls back to fallback_gap_assessments() on any failure.
    """
    try:
        from pydantic import BaseModel as PydanticBaseModel
        from pydantic_ai import Agent

        class GapAssessmentItem(PydanticBaseModel):
            gap_id: str
            relevance: str  # critical | relevant | minor | irrelevant
            could_change_conclusion: bool
            reason: str

        class GapAssessmentResponse(PydanticBaseModel):
            assessments: list[GapAssessmentItem]

        prompt = _build_gap_assessment_prompt(hypothesis, scored_claims, gaps, observations)

        agent = Agent(
            model=model or "anthropic:claude-sonnet-4-20250514",
            output_type=GapAssessmentResponse,
        )
        result = await agent.run(prompt)

        # Convert to domain GapAssessment objects with validation
        assessments: list[GapAssessment] = []
        valid_relevance = {"critical", "relevant", "minor", "irrelevant"}
        for item in result.output.assessments:
            relevance = item.relevance if item.relevance in valid_relevance else "relevant"
            assessments.append(GapAssessment(
                gap_id=item.gap_id,
                relevance=relevance,
                could_change_conclusion=item.could_change_conclusion,
                reason=item.reason,
            ))
        return assessments

    except Exception:
        return fallback_gap_assessments(gaps)


async def _llm_narrative(
    hypothesis,
    claims,
    cov_envelope: dict,
    question: str,
    model: str | None,
) -> NarrativeResult:
    """Generate narrative text using an LLM.

    Lazy-imports pydantic-ai to avoid requiring it for mechanical mode.
    Falls back to mechanical narrative on import or API errors.
    """
    try:
        from pydantic import BaseModel as PydanticBaseModel
        from pydantic_ai import Agent

        class Narrative(PydanticBaseModel):
            hypothesis_text: str
            likelihood_rationale: str
            confidence_rationale: str
            gaps: list[str]
            next_steps: list[str]

        supporting = [c for c in claims if c.polarity == "supports"]
        contradicting = [c for c in claims if c.polarity == "contradicts"]
        cov_status = cov_envelope.get("coverage_report", {}).get("overall_status", "unknown")

        prompt = (
            f"You are a security analyst summarizing an investigation.\n\n"
            f"Investigation question: {question}\n\n"
            f"Hypothesis: {hypothesis.statement}\n"
            f"Likelihood: {hypothesis.likelihood}\n"
            f"Confidence: {hypothesis.confidence}\n\n"
            f"Supporting claims ({len(supporting)}):\n"
        )
        for c in supporting:
            prompt += f"  - {c.statement} (confidence={c.confidence})\n"
        if contradicting:
            prompt += f"\nContradicting claims ({len(contradicting)}):\n"
            for c in contradicting:
                prompt += f"  - {c.statement} (confidence={c.confidence})\n"
        prompt += f"\nCoverage status: {cov_status}\n"

        if hypothesis.gap_assessments:
            prompt += "\nGap assessments:\n"
            for ga in hypothesis.gap_assessments:
                prompt += f"  - {ga.gap_id}: {ga.relevance} (could_change={ga.could_change_conclusion}) -- {ga.reason}\n"

        prompt += (
            "\nWrite a concise narrative with:\n"
            "- hypothesis_text: one-sentence hypothesis statement\n"
            "- likelihood_rationale: what the evidence suggests\n"
            "- confidence_rationale: what can/cannot be verified, referencing gap assessments\n"
            "- gaps: list of data gaps\n"
            "- next_steps: recommended follow-ups\n"
        )

        agent = Agent(
            model=model or "anthropic:claude-sonnet-4-20250514",
            output_type=Narrative,
        )
        result = await agent.run(prompt)
        n = result.output
        return NarrativeResult(
            hypothesis_text=n.hypothesis_text,
            likelihood_rationale=n.likelihood_rationale,
            confidence_rationale=n.confidence_rationale,
            gaps=n.gaps,
            next_steps=n.next_steps,
        )
    except Exception:
        # Fall back to mechanical narrative
        return build_narrative(hypothesis, claims, cov_envelope)
