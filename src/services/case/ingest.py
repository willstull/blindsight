"""Ingest normalized records into the case store.

All INSERT statements specify every column explicitly (including ingested_at)
to avoid NOT NULL violations on INSERT OR REPLACE.
"""
import json
import logging
from datetime import datetime, timezone

import duckdb

from src.services.case.json_helpers import to_json
from src.types.core import (
    Entity, ActionEvent, Relationship, CoverageReport,
    EvidenceItem, Claim, Assumption, Hypothesis,
)
from src.types.result import Result, Ok, Err
from src.utils.ulid import generate_ulid


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest_entities(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    entities: list[Entity],
) -> Result[int, Exception]:
    """Upsert entities. Returns count ingested."""
    try:
        now = _now_ts()
        for e in entities:
            refs_json = to_json([r.model_dump(exclude_none=True) for r in e.refs]) if e.refs else "[]"
            attrs_json = to_json(e.attributes)
            conn.execute(
                """INSERT INTO entities
                   (id, tlp, entity_type, kind, display_name, refs, attributes,
                    first_seen, last_seen, confidence, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    tlp=EXCLUDED.tlp, entity_type=EXCLUDED.entity_type,
                    kind=EXCLUDED.kind, display_name=EXCLUDED.display_name,
                    refs=EXCLUDED.refs, attributes=EXCLUDED.attributes,
                    first_seen=EXCLUDED.first_seen, last_seen=EXCLUDED.last_seen,
                    confidence=EXCLUDED.confidence, ingested_at=EXCLUDED.ingested_at""",
                [
                    e.id, e.tlp, e.entity_type, e.kind, e.display_name,
                    refs_json, attrs_json,
                    e.first_seen, e.last_seen, e.confidence, now,
                ],
            )
        logger.info("Ingested entities", extra={"count": len(entities)})
        return Ok(len(entities))
    except Exception as e:
        logger.error("Entity ingest failed", extra={"error": str(e)})
        return Err(e)


def ingest_events(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    events: list[ActionEvent],
) -> Result[int, Exception]:
    """Upsert events. Returns count ingested."""
    try:
        now = _now_ts()
        for ev in events:
            actor_json = to_json(ev.actor.model_dump(exclude_none=True))
            targets_json = to_json([t.model_dump(exclude_none=True) for t in ev.targets]) if ev.targets else "[]"
            raw_refs_json = to_json([r.model_dump(exclude_none=True) for r in ev.raw_refs]) if ev.raw_refs else "[]"
            conn.execute(
                """INSERT INTO events
                   (id, tlp, domain, ts, action, actor, targets, outcome,
                    raw_refs, context, related_entity_ids, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    tlp=EXCLUDED.tlp, domain=EXCLUDED.domain, ts=EXCLUDED.ts,
                    action=EXCLUDED.action, actor=EXCLUDED.actor,
                    targets=EXCLUDED.targets, outcome=EXCLUDED.outcome,
                    raw_refs=EXCLUDED.raw_refs, context=EXCLUDED.context,
                    related_entity_ids=EXCLUDED.related_entity_ids,
                    ingested_at=EXCLUDED.ingested_at""",
                [
                    ev.id, ev.tlp, ev.domain, ev.ts, ev.action,
                    actor_json, targets_json, ev.outcome,
                    raw_refs_json, to_json(ev.context),
                    to_json(ev.related_entity_ids), now,
                ],
            )
        logger.info("Ingested events", extra={"count": len(events)})
        return Ok(len(events))
    except Exception as e:
        logger.error("Event ingest failed", extra={"error": str(e)})
        return Err(e)


def ingest_relationships(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    rels: list[Relationship],
) -> Result[int, Exception]:
    """Upsert relationships. Returns count ingested."""
    try:
        now = _now_ts()
        for r in rels:
            evidence_refs_json = None
            if r.evidence_refs is not None:
                evidence_refs_json = to_json([ref.model_dump(exclude_none=True) for ref in r.evidence_refs])
            conn.execute(
                """INSERT INTO relationships
                   (id, tlp, domain, relationship_type, from_entity_id, to_entity_id,
                    first_seen, last_seen, evidence_refs, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    tlp=EXCLUDED.tlp, domain=EXCLUDED.domain,
                    relationship_type=EXCLUDED.relationship_type,
                    from_entity_id=EXCLUDED.from_entity_id,
                    to_entity_id=EXCLUDED.to_entity_id,
                    first_seen=EXCLUDED.first_seen, last_seen=EXCLUDED.last_seen,
                    evidence_refs=EXCLUDED.evidence_refs,
                    ingested_at=EXCLUDED.ingested_at""",
                [
                    r.id, r.tlp, r.domain, r.relationship_type,
                    r.from_entity_id, r.to_entity_id,
                    r.first_seen, r.last_seen, evidence_refs_json, now,
                ],
            )
        logger.info("Ingested relationships", extra={"count": len(rels)})
        return Ok(len(rels))
    except Exception as e:
        logger.error("Relationship ingest failed", extra={"error": str(e)})
        return Err(e)


def ingest_coverage_report(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    coverage: CoverageReport,
) -> Result[str, Exception]:
    """Upsert a coverage report. Returns the report ID."""
    try:
        now = _now_ts()
        sources_json = to_json([s.model_dump(exclude_none=True) for s in coverage.sources]) if coverage.sources else "[]"
        conn.execute(
            """INSERT INTO coverage_reports
               (id, tlp, domain, time_range_start, time_range_end, overall_status,
                sources, missing_fields, data_latency_seconds, quality_flags, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                tlp=EXCLUDED.tlp, domain=EXCLUDED.domain,
                time_range_start=EXCLUDED.time_range_start,
                time_range_end=EXCLUDED.time_range_end,
                overall_status=EXCLUDED.overall_status,
                sources=EXCLUDED.sources,
                missing_fields=EXCLUDED.missing_fields,
                data_latency_seconds=EXCLUDED.data_latency_seconds,
                quality_flags=EXCLUDED.quality_flags,
                notes=EXCLUDED.notes, created_at=EXCLUDED.created_at""",
            [
                coverage.id, coverage.tlp, coverage.domain,
                coverage.time_range.start, coverage.time_range.end,
                coverage.overall_status, sources_json,
                to_json(coverage.missing_fields),
                coverage.data_latency_seconds,
                to_json(coverage.quality_flags),
                coverage.notes, now,
            ],
        )
        logger.info("Ingested coverage report", extra={"report_id": coverage.id})
        return Ok(coverage.id)
    except Exception as e:
        logger.error("Coverage report ingest failed", extra={"error": str(e)})
        return Err(e)


def ingest_evidence_items(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    items: list[EvidenceItem],
) -> Result[int, Exception]:
    """Upsert evidence items. Returns count ingested."""
    try:
        now = _now_ts()
        for item in items:
            raw_refs_json = to_json(
                [r.model_dump(exclude_none=True) for r in item.raw_refs]
            ) if item.raw_refs else "[]"
            conn.execute(
                """INSERT INTO evidence_items
                   (id, tlp, domain, summary, raw_refs, collected_at,
                    related_entity_ids, related_event_ids, hash, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    tlp=EXCLUDED.tlp, domain=EXCLUDED.domain,
                    summary=EXCLUDED.summary, raw_refs=EXCLUDED.raw_refs,
                    collected_at=EXCLUDED.collected_at,
                    related_entity_ids=EXCLUDED.related_entity_ids,
                    related_event_ids=EXCLUDED.related_event_ids,
                    hash=EXCLUDED.hash, ingested_at=EXCLUDED.ingested_at""",
                [
                    item.id, item.tlp, item.domain, item.summary,
                    raw_refs_json, item.collected_at,
                    to_json(item.related_entity_ids),
                    to_json(item.related_event_ids),
                    item.hash, now,
                ],
            )
        logger.info("Ingested evidence items", extra={"count": len(items)})
        return Ok(len(items))
    except Exception as e:
        logger.error("Evidence item ingest failed", extra={"error": str(e)})
        return Err(e)


def ingest_claims(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    claims: list[Claim],
) -> Result[int, Exception]:
    """Upsert claims. Returns count ingested."""
    try:
        now = _now_ts()
        for c in claims:
            conn.execute(
                """INSERT INTO claims
                   (id, tlp, statement, polarity, confidence,
                    backed_by_evidence_ids, subject_entity_ids,
                    time_range_start, time_range_end,
                    derived_from_claim_ids, assumption_ids, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    tlp=EXCLUDED.tlp, statement=EXCLUDED.statement,
                    polarity=EXCLUDED.polarity, confidence=EXCLUDED.confidence,
                    backed_by_evidence_ids=EXCLUDED.backed_by_evidence_ids,
                    subject_entity_ids=EXCLUDED.subject_entity_ids,
                    time_range_start=EXCLUDED.time_range_start,
                    time_range_end=EXCLUDED.time_range_end,
                    derived_from_claim_ids=EXCLUDED.derived_from_claim_ids,
                    assumption_ids=EXCLUDED.assumption_ids,
                    created_at=EXCLUDED.created_at""",
                [
                    c.id, c.tlp, c.statement, c.polarity, c.confidence,
                    to_json(c.backed_by_evidence_ids),
                    to_json(c.subject_entity_ids),
                    c.time_range.start if c.time_range else None,
                    c.time_range.end if c.time_range else None,
                    to_json(c.derived_from_claim_ids),
                    to_json(c.assumption_ids), now,
                ],
            )
        logger.info("Ingested claims", extra={"count": len(claims)})
        return Ok(len(claims))
    except Exception as e:
        logger.error("Claim ingest failed", extra={"error": str(e)})
        return Err(e)


def ingest_assumptions(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    assumptions: list[Assumption],
) -> Result[int, Exception]:
    """Upsert assumptions. Returns count ingested."""
    try:
        now = _now_ts()
        for a in assumptions:
            conn.execute(
                """INSERT INTO assumptions
                   (id, tlp, statement, strength, rationale, impacts, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    tlp=EXCLUDED.tlp, statement=EXCLUDED.statement,
                    strength=EXCLUDED.strength, rationale=EXCLUDED.rationale,
                    impacts=EXCLUDED.impacts, created_at=EXCLUDED.created_at""",
                [
                    a.id, a.tlp, a.statement, a.strength, a.rationale,
                    to_json(a.impacts), now,
                ],
            )
        logger.info("Ingested assumptions", extra={"count": len(assumptions)})
        return Ok(len(assumptions))
    except Exception as e:
        logger.error("Assumption ingest failed", extra={"error": str(e)})
        return Err(e)


def ingest_hypotheses(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    hypotheses: list[Hypothesis],
) -> Result[int, Exception]:
    """Upsert hypotheses. Returns count ingested."""
    try:
        now = _now_ts()
        for h in hypotheses:
            conn.execute(
                """INSERT INTO hypotheses
                   (id, tlp, iq_id, statement, likelihood, confidence,
                    supporting_claim_ids, contradicting_claim_ids, gaps,
                    gap_assessments, next_evidence_requests,
                    status, updated_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                    tlp=EXCLUDED.tlp, iq_id=EXCLUDED.iq_id,
                    statement=EXCLUDED.statement,
                    likelihood=EXCLUDED.likelihood,
                    confidence=EXCLUDED.confidence,
                    supporting_claim_ids=EXCLUDED.supporting_claim_ids,
                    contradicting_claim_ids=EXCLUDED.contradicting_claim_ids,
                    gaps=EXCLUDED.gaps,
                    gap_assessments=EXCLUDED.gap_assessments,
                    next_evidence_requests=EXCLUDED.next_evidence_requests,
                    status=EXCLUDED.status, updated_at=EXCLUDED.updated_at,
                    created_at=EXCLUDED.created_at""",
                [
                    h.id, h.tlp, h.iq_id, h.statement,
                    h.likelihood, h.confidence,
                    to_json(h.supporting_claim_ids),
                    to_json(h.contradicting_claim_ids),
                    to_json(h.gaps),
                    to_json([ga.model_dump() for ga in h.gap_assessments]),
                    to_json(h.next_evidence_requests),
                    h.status, h.updated_at or now, now,
                ],
            )
        logger.info("Ingested hypotheses", extra={"count": len(hypotheses)})
        return Ok(len(hypotheses))
    except Exception as e:
        logger.error("Hypothesis ingest failed", extra={"error": str(e)})
        return Err(e)


def ingest_domain_response(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    response: dict,
) -> Result[dict, Exception]:
    """Ingest a domain tool response (entities, events, relationships, coverage).

    Processes in FK order: entities -> events -> relationships -> coverage.
    Returns summary counts.
    """
    try:
        counts = {"entities": 0, "events": 0, "relationships": 0, "coverage_reports": 0}

        # Parse and ingest entities
        raw_entities = response.get("entities", [])
        if raw_entities:
            entities = [Entity.model_validate(e) if isinstance(e, dict) else e for e in raw_entities]
            result = ingest_entities(logger, conn, entities)
            if result.is_err():
                return Err(result.err())
            counts["entities"] = result.ok()

        # Parse and ingest events
        raw_events = response.get("events", [])
        if raw_events:
            events = [ActionEvent.model_validate(e) if isinstance(e, dict) else e for e in raw_events]
            result = ingest_events(logger, conn, events)
            if result.is_err():
                return Err(result.err())
            counts["events"] = result.ok()

        # Parse and ingest relationships
        raw_rels = response.get("relationships", [])
        if raw_rels:
            rels = [Relationship.model_validate(r) if isinstance(r, dict) else r for r in raw_rels]
            result = ingest_relationships(logger, conn, rels)
            if result.is_err():
                return Err(result.err())
            counts["relationships"] = result.ok()

        # Parse and ingest coverage report
        raw_coverage = response.get("coverage_report")
        if raw_coverage:
            coverage = CoverageReport.model_validate(raw_coverage) if isinstance(raw_coverage, dict) else raw_coverage
            result = ingest_coverage_report(logger, conn, coverage)
            if result.is_err():
                return Err(result.err())
            counts["coverage_reports"] = 1

        logger.info("Ingested domain response", extra=counts)
        return Ok(counts)
    except Exception as e:
        logger.error("Domain response ingest failed", extra={"error": str(e)})
        return Err(e)


def record_tool_call(
    logger: logging.Logger,
    conn: duckdb.DuckDBPyConnection,
    case_id: str,
    request_id: str,
    domain: str,
    tool_name: str,
    request_params: dict,
    response_status: str,
    response_body: dict,
    coverage_report_id: str | None = None,
    duration_ms: int | None = None,
) -> Result[str, Exception]:
    """Record a tool call for reproducibility. Returns the tool call ID."""
    try:
        tool_call_id = generate_ulid()
        now = _now_ts()
        conn.execute(
            """INSERT INTO tool_calls
               (id, case_id, request_id, domain, tool_name, request_params,
                response_status, response_body, coverage_report_id, executed_at, duration_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                tool_call_id, case_id, request_id, domain, tool_name,
                to_json(request_params), response_status, to_json(response_body),
                coverage_report_id, now, duration_ms,
            ],
        )
        logger.info("Recorded tool call", extra={"tool_call_id": tool_call_id, "tool_name": tool_name})
        return Ok(tool_call_id)
    except Exception as e:
        logger.error("Tool call recording failed", extra={"error": str(e)})
        return Err(e)
