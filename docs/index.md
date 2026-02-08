# Blindsight Documentation

## Specifications

Stable interfaces and invariants:

- [Ontology](spec/ontology.yaml) - Core domain-agnostic data model
- [Identity Plane Contract](spec/identity_plane_contract.json) - MCP tool specifications
- [Canonical Output Specification](spec/canonical-output-spec.md) - Universal response envelope
- [Replay Dataset Contract](spec/replay-dataset-contract.md) - Replay dataset format
- [Source Adapter Interface](spec/source-adapter-interface.md) - Plane adapter boundary
- [Case Store Schema](spec/case-store-schema.md) - DuckDB tables

### Implementation

- [Code Organization](spec/implementation/code-organization.md) - Structure, coding patterns, project scope
- [FastMCP and Pydantic-AI Patterns](spec/implementation/fastmcp-pydantic-patterns.md) - MCP tech stack

## Architecture Decision Records

- [ADR-0001: Read-Only Query-in-Place](adr/ADR-0001-read-only-query-in-place.md)
- [ADR-0002: Replay Datasets for Evaluation](adr/ADR-0002-replay-datasets-for-evaluation.md)
- [ADR-0003: DuckDB as Case Store](adr/ADR-0003-duckdb-as-case-store.md)
- [ADR-0004: Plane-Based Architecture](adr/ADR-0004-plane-based-architecture.md)
- [ADR-0005: Gap-Aware Hypothesis Scoring](adr/ADR-0005-gap-aware-hypothesis-scoring.md)
- [ADR-0006: MCP Tool Contracts](adr/ADR-0006-mcp-tool-contracts.md)

## Project Status

- [Project Boundary](project-boundary.md) - Scope and success criteria
- [Roadmap](roadmap.md) - Milestones and outcomes
- [Status](status.md) - Current state and next actions

## Evaluation

- [Replay Scenarios](replay-scenarios.md) - 12 scenario families (48 test cases)
- [Live Integration Framework](live-integration-framework.md) - Decision framework for live sources
