# Project Boundary and Success Criteria

## Project Summary

Blindsight is a hypothesis-driven incident investigation system that demonstrates evidence normalization, correlation, and gap-aware confidence scoring. It queries existing telemetry systems in place and maintains case-scoped evidence records for reproducibility.

## In Scope

**Core Components:**
- Identity domain MCP server (replay-backed, optionally live-backed)
- Case MCP server (DuckDB-backed persistence and correlation)
- Replay dataset format with baseline and degraded variants
- Coverage report generation (explicit gap tracking)
- Coverage-aware hypothesis scoring (likelihood vs confidence limit)

**Implementation Scope:**
- Tool contracts + schema discipline (12 identity tools, 5+ case tools)
- Replay dataset format (NDJSON fixtures with coverage metadata)
- Deterministic evaluation harness with degraded variants (6+ scenarios)
- Case record persistence (DuckDB with entities, events, relationships, claims, hypotheses)
- Normalization + normalized IDs + correlation pivots
- Coverage/missing-data reporting (machine-readable and human-readable)
- Regression tests (golden output comparison)

**Evaluation:**
- 6+ replay scenarios (3 baseline, 3+ degraded)
- Deterministic: same inputs produce identical outputs
- Traceable: every claim links to evidence links to raw source
- Coverage-aware: missing data reduces confidence limits (verified with degraded variants)

## Out of Scope

**Not building:**
- Enterprise-wide continuous ingestion or indexing (queries existing systems in-place)
- Long-term log lake or analytics store for organization
- Primary query/search UI for logs (Splunk/Datadog/etc. remain that)
- ML anomaly detection
- Automated remediation
- Many integrations (one evidence domain proves the pattern)
- Full ITSM/case management

**System will NOT claim:**
- Omniscient visibility (honest about gaps)
- Real-time alerting or detection
- Automated response or containment
- Complete telemetry coverage

**System WILL claim:**
- Normalized view of available evidence
- Explicit tracking of what can and cannot be verified
- Reproducible investigations via tool-call history
- Correlation across entities/events within a case
- Coverage-aware confidence limits on conclusions

## Success Criteria (End of Semester)

**Technical Deliverables:**
1. Two working MCP servers (identity domain + case MCP server)
2. Replay integration implementing DomainIntegration interface
3. 6+ replay scenarios (baseline + degraded variants)
4. DuckDB case store with correlation queries working
5. Golden output comparison working (regression detection)
6. Unit + integration tests passing
7. Coverage reports generated for all queries

**Evaluation Metrics:**
1. **Deterministic**: 10 runs of same scenario produce identical outputs (verified)
2. **Traceable**: Every claim → evidence → raw source (verified via source references)
3. **Coverage-aware**: Degraded variants produce reduced confidence (verified)
4. **Reproducible**: Tool-call history enables investigation replay

**Documentation:**
1. All specs written and stable (ontology, contracts, adapters)
2. Architecture decisions recorded (6 ADRs minimum)
3. Evaluation strategy documented (replay format, scenarios, metrics)
4. Writeup explaining design, evaluation results, limitations

**Demo:**
1. Run replay scenario with complete coverage (high confidence output)
2. Run same scenario with degraded data (reduced confidence, limitations visible)
3. Show correlation query in case store (entity → neighbors, actor → events)
4. Show tool-call history and reproducibility

## What Constitutes "Done"

**Minimum viable practicum:**
- Identity domain returns deterministic results from replay fixtures
- Case MCP server stores and correlates normalized records
- 3 baseline scenarios pass with expected outputs
- 3 degraded scenarios show reduced confidence limits
- Documentation complete (specs, ADRs, writeup)

**Stretch goals (if time permits):**
- One live source integration (Okta, AWS CloudTrail, or Azure AD)
- Claims/hypotheses generation (beyond just storing entities/events)
- 10+ replay scenarios covering more investigation patterns
- Performance benchmarks on replay execution time

## Live Integration Decision (Deferred)

Decision deferred until replay evaluation harness is working. Live integration is optional for demonstrating the system; replay datasets prove the architecture without dependency on external systems.

If pursued, candidate sources: Okta (identity provider), AWS CloudTrail (cloud audit), Azure AD (identity provider). Selection criteria: API stability, authentication feasibility, ability to script test scenarios.
