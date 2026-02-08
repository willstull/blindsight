# Blindsight

> Investigation sight for responders in the dark

**Author**: Will Stull

## Project Overview

Incident responders are often **blind** during active investigations: evidence scattered across identity providers, cloud audit logs, and application systems; retention gaps obscure critical windows; time pressure prevents methodical correlation.

**Blindsight** restores structured vision by normalizing telemetry into canonical entities, events, and relationships—with explicit tracking of what can and cannot be verified. The system doesn't claim omniscience: it provides clear sight where data exists, and honest gaps where it doesn't.

Blindsight helps responders answer scope, containment, and timeline questions by querying systems already in place (IdP, cloud audit, app logs) and recording evidence and gaps. Blindsight does not run continuous, organization-wide ingestion; it maintains a case-scoped evidence record (snapshots and references) to make investigations reproducible.

### Key Principles

1. **Restores Vision**: Normalizes fragmented telemetry into coherent investigation view
2. **Hypothesis-Driven**: Investigation questions and hypothesis templates defined as data (Knowledge Packs), not code
3. **Honest Gaps**: Coverage reports explicitly surface missing data, retention gaps, and confidence limits (not blind confidence)
4. **Evidence Traceability**: Every conclusion links back to raw sources with provenance tracking
5. **Query-in-Place**: Read-only MCP adapters normalize results from existing telemetry systems

## Architecture Components

### Data Model (from `ontology.yaml`)
- **Planes**: Modular investigation domains (identity, network, resource)
- **Canonical Objects**: Entity, ActionEvent, Relationship, CoverageReport, Evidence, Claim, Hypothesis, Case
- **Gap-Aware Conclusions**: Hypotheses include likelihood scores AND confidence caps based on missing data

### Identity Plane Contract (from `identity_plane_contract.json`)
- MCP tools for identity investigation (resolve_principal, search_events, get_neighbors, etc.)
- Every response includes a coverage_report (even if "unknown")
- Standardized response envelope with entities, events, relationships

### Storage
- DuckDB for case record persistence and correlation
- Tool-call history for reproducibility

## Documentation

See **[docs/index.md](docs/index.md)** for complete documentation index.

### Specifications
- [Ontology](docs/spec/ontology.yaml) - Core data model
- [Identity Plane Contract](docs/spec/identity_plane_contract.json) - MCP tool specs
- [Canonical Output Spec](docs/spec/canonical-output-spec.md) - Response envelope
- [Replay Dataset Contract](docs/spec/replay-dataset-contract.md) - Evaluation format
- [Source Adapter Interface](docs/spec/source-adapter-interface.md) - Plane adapter boundary

### Architecture Decisions
- [ADR-0001: Read-Only Query-in-Place](docs/adr/ADR-0001-read-only-query-in-place.md)
- [ADR-0002: Replay Datasets for Evaluation](docs/adr/ADR-0002-replay-datasets-for-evaluation.md)
- [ADR-0003: DuckDB as Case Store](docs/adr/ADR-0003-duckdb-as-case-store.md)
- [ADR-0004: Plane-Based Architecture](docs/adr/ADR-0004-plane-based-architecture.md)
- [ADR-0005: Gap-Aware Hypothesis Scoring](docs/adr/ADR-0005-gap-aware-hypothesis-scoring.md)
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
- **Explicit gap handling**: Missing data reflected in limited-strength conclusions (gap-aware confidence)
- **Golden output comparison**: Regression detection via exact output matching

## Current Status

See [docs/status.md](docs/status.md) for current state.

**Done**: Specifications written, architecture decisions recorded, repository structured.

**Next**: Milestone 1 - Replay-backed identity server implementation.

## Design Constraints

**In Scope**:
- Core data model + rule set format
- One MCP adapter (identity plane) backed by replay dataset or one live source
- Case-scoped evidence record:
  - Tool calls executed (inputs/outputs, timestamps)
  - Pointers to raw sources (URLs, query IDs, event IDs)
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
- Many integrations (one adapter proves the pattern)
- Full ITSM/case management (investigation substrate, not ticketing)
