# Blindsight

> Investigation sight for responders in the dark

**Author**: Will Stull

## Project Overview

Incident responders are often **blind** during active investigations: evidence scattered across identity providers, cloud audit logs, and application systems; retention gaps obscure critical windows; time pressure prevents methodical correlation.

**Blindsight** restores structured vision by normalizing telemetry into normalized entities, events, and relationships—with explicit tracking of what can and cannot be verified. The system doesn't claim omniscience: it provides clear sight where data exists, and honest gaps where it doesn't.

Blindsight helps responders answer scope, containment, and timeline questions by querying systems already in place (IdP, cloud audit, app logs) and recording evidence and gaps. Blindsight does not run continuous, organization-wide ingestion; it maintains a case-scoped evidence record (snapshots and source references) to make investigations reproducible.

### Key Principles

1. **Restores Vision**: Normalizes fragmented telemetry into coherent investigation view
2. **Hypothesis-Driven**: Investigation questions and hypothesis templates defined as data (Knowledge Packs), not code
3. **Honest Gaps**: Coverage reports explicitly surface missing data, retention gaps, and confidence limits (not blind confidence)
4. **Evidence Traceability**: Every conclusion links back to raw sources with source reference tracking
5. **Query-in-Place**: Read-only MCP integrations normalize results from existing telemetry systems

## Architecture Components

### Data Model (from `ontology.yaml`)
- **Domains**: Modular investigation domains (identity, network, cloud infrastructure, SaaS, application, etc.)
- **Normalized Records**: Entity, ActionEvent, Relationship, CoverageReport, Evidence, Claim, Hypothesis, Case
- **Coverage-Aware Conclusions**: Hypotheses include likelihood scores AND confidence limits based on missing data

### Identity Domain Contract (from `identity-domain-contract.json`)
- MCP tools for identity investigation (describe_domain, search_events, get_entity, get_neighbors, etc.)
- Every response includes a coverage_report (even if "unknown")
- Standardized response envelope with entities, events, relationships

### Storage
- DuckDB for case record persistence and correlation
- Tool-call history for reproducibility

## Documentation

See **[docs/index.md](docs/index.md)** for complete documentation index.

### Specifications
- [Ontology](docs/spec/ontology.yaml) - Core data model
- [Identity Domain Contract](docs/spec/identity-domain-contract.json) - MCP tool specs
- [Normalized Output Spec](docs/spec/normalized-output-spec.md) - Response envelope
- [Replay Dataset Contract](docs/spec/replay-dataset-contract.md) - Evaluation format
- [Integration Interface](docs/spec/integration-interface.md) - Domain integration boundary

### Architecture Decisions
- [ADR-0001: Read-Only Query-in-Place](docs/adr/ADR-0001-read-only-query-in-place.md)
- [ADR-0002: Replay Datasets for Evaluation](docs/adr/ADR-0002-replay-datasets-for-evaluation.md)
- [ADR-0003: DuckDB as Case Store](docs/adr/ADR-0003-duckdb-as-case-store.md)
- [ADR-0004: Domain-Based Architecture](docs/adr/ADR-0004-domain-based-architecture.md)
- [ADR-0005: Coverage-Aware Hypothesis Scoring](docs/adr/ADR-0005-gap-aware-hypothesis-scoring.md)
- [ADR-0006: MCP Tool Contracts](docs/adr/ADR-0006-mcp-tool-contracts.md)

### Project Status
- [Roadmap](docs/roadmap.md) - Milestones and outcomes
- [Status](docs/status.md) - Current state and next actions

## Target Use Cases

**When responders are "blind" due to**:
- Fragmented evidence across disconnected systems (IdP, cloud audit, app logs)
- Retention gaps obscuring critical time windows
- Missing fields or disabled logging
- Time pressure preventing manual correlation

**Blindsight helps answer**:
- Account compromise: What actions did this principal take?
- Privilege escalation: Did credentials or permissions change?
- Scope determination: What happened leading up to detection?
- Containment verification: Are we confident the threat is contained?

## Evaluation Approach

**Testing vision restoration without real incidents**:
- **Replay datasets**: Scripted scenarios with known outcomes (baseline + degraded variants)
- **Reproducible outputs**: Same inputs → same structured outputs (deterministic)
- **Explicit gap handling**: Missing data reflected in limited-strength conclusions (coverage-aware confidence)
- **Golden output comparison**: Regression detection via exact output matching

## Current Status

See [docs/status.md](docs/status.md) for current state.

**Done**: Specifications written, architecture decisions recorded, repository structured.

**Next**: Milestone 1 - Replay-backed identity domain MCP server implementation.

## Design Constraints

**In Scope**:
- Core data model + rule set format
- One MCP integration (identity domain) backed by replay dataset or one live source
- Case-scoped evidence record:
  - Tool calls executed (inputs/outputs, timestamps)
  - Source references pointing to raw sources (URLs, query IDs, event IDs)
  - Selected evidence artifacts (exports, snapshots, small log slices) for reproducibility
  - Derived objects (entities/events/relationships), claims, hypotheses, coverage reports
- Investigation questions + hypothesis templates (2-3 questions)
- Demonstration on replay dataset plus degraded-data variants

**Out of Scope**:
- Long-term log lake or analytics store for the organization
- Continuous ingestion/indexing of all logs/telemetry across systems
- Primary query/search UI for logs (Splunk/Datadog/etc. remain that)
- ML anomaly detection (structured investigation, not magic)
- Automated remediation (provide sight, not action)
- Many integrations (one integration proves the pattern)
- Full ITSM/case management (investigation system, not ticketing)
