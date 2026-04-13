# ADR-0011: Incident Report Generation

**Status**: accepted

## Context

The investigation pipeline produces structured data (hypothesis, claims, evidence items, gap assessments) but no consumable analyst artifact. Investigation results were returned in-memory as an InvestigationReport but analysis artifacts (evidence_items, claims, hypotheses) were not persisted to the case store, making reports non-reproducible from saved cases.

Analysts need a repeatable incident report that:
- Can be regenerated from the saved case at any time
- Separates deterministic facts from narrative prose
- Includes all evidence, coverage, gaps, and reproducibility data
- Follows established incident response frameworks

## Decision

Add a report generation service that:

1. **Persists analysis artifacts** during the pipeline: evidence_items, claims, hypotheses, and investigation metadata are ingested into the case store after scoring and narrative.

2. **Collects facts from the case store**: A `get_report_facts` query function returns all report data in one payload. A corresponding MCP tool (`get_report_facts_tool`) exposes this via the case server.

3. **Renders deterministic Markdown**: A `render_report()` function produces a 9-section report from `ReportFacts`. Deterministic code owns structure, evidence selection, event ordering, totals, coverage, tool-call history, and section membership.

4. **Optionally generates LLM prose**: `generate_report_prose()` calls an LLM with a grounding contract to produce narrative for 4 sections (executive summary, key findings, hypothesis explanation, recommended follow-up). Falls back to deterministic prose on failure.

5. **Exposes via MCP**: A `generate_report` tool on the investigation server proxies to the case server for facts, then renders the report.

### Report sections (NIST SP 800-61 Rev. 3 / CSF 2.0 aligned)

1. Executive Summary
2. Scope
3. Key Findings
4. Timeline
5. Evidence Assessment
6. Hypothesis Assessment
7. Impact and Exposure
8. Recommended Follow-Up
9. Reproducibility Appendix

### Key design choices

- **File-based migrations**: SQL migration files in `src/services/case/migrations/` discovered by version number. Replaces hardcoded string constants.
- **Investigation metadata column**: `ALTER TABLE cases ADD COLUMN investigation_metadata JSON` stores scenario context, focal principals, rationale, and domains.
- **Two-phase ReportFacts**: Parse the case store payload, then compute derived fields (impact totals from app event context).
- **Transaction actions**: Only `app.invoice.create` and `app.payment.create` contribute to impact totals.
- **MCP boundary**: The investigation server never opens DuckDB directly. Report generation proxies through the case MCP server.
- **Persist step not budget-gated**: Analysis artifact ingestion happens unconditionally after narrative generation.

## Rationale

- Reproducibility from saved case is a core requirement. Persisting analysis artifacts closes the gap where claims and evidence were computed in memory but never saved.
- NIST SP 800-61 Rev. 3 alignment provides a defensible section structure without requiring visible control mappings.
- Hybrid deterministic/LLM model prevents the LLM from inventing facts while allowing it to produce readable prose.
- File-based migrations scale better than string constants and follow standard database practices.

## Consequences

- Case store schema bumped to version 3 (investigation_metadata column).
- Pipeline makes one additional MCP call per investigation (analysis artifact persist).
- Report generation requires a completed investigation with persisted artifacts.
- LLM prose is optional; deterministic-only reports are always available.
