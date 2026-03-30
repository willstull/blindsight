# Blindsight Documentation

## Specifications

Stable interfaces and invariants:

- [Ontology](spec/ontology.yaml) - Core domain-agnostic data model
- [Identity Domain Contract](spec/identity-domain-contract.json) - MCP tool specifications
- [Normalized Output Specification](spec/normalized-output-spec.md) - Universal response envelope
- [Replay Dataset Contract](spec/replay-dataset-contract.md) - Replay dataset format
- [Integration Interface](spec/integration-interface.md) - Domain integration boundary
- [Case Store Schema](spec/case-store-schema.md) - DuckDB tables
- [Case MCP Tool Contract](spec/case-mcp-tool-contract.md) - Case server pivot tools
- [Investigation MCP Tool Contract](spec/investigation-mcp-tool-contract.md) - Investigation server tools

### Implementation

- [Code Organization](spec/implementation/code-organization.md) - Structure, coding patterns, project scope
- [FastMCP and Pydantic-AI Patterns](spec/implementation/fastmcp-pydantic-patterns.md) - MCP tech stack

## Architecture Decision Records

- [ADR-0001: Read-Only Query-in-Place](adr/ADR-0001-read-only-query-in-place.md)
- [ADR-0002: Replay Datasets for Evaluation](adr/ADR-0002-replay-datasets-for-evaluation.md)
- [ADR-0003: DuckDB as Case Store](adr/ADR-0003-duckdb-as-case-store.md)
- [ADR-0004: Domain-Based Architecture](adr/ADR-0004-domain-based-architecture.md)
- [ADR-0005: Coverage-Aware Hypothesis Scoring](adr/ADR-0005-gap-aware-hypothesis-scoring.md)
- [ADR-0006: MCP Tool Contracts](adr/ADR-0006-mcp-tool-contracts.md)
- [ADR-0007: Investigation Orchestration Server](adr/ADR-0007-investigation-orchestration-server.md)
- [ADR-0008: Investigation Follow-up Tools](adr/ADR-0008-investigation-followup-tools.md)

## Project Information

- [Project Boundary](project-boundary.md) - Scope and success criteria
- [Roadmap](roadmap.md) - Milestones and outcomes
- [Status](status.md) - Current state and next actions
- [Appendix](appendix.md) - Comprehensive list of terms

## Evaluation

- [Replay Scenarios](replay-scenarios.md) - 12 scenario families (48 test cases)
- [Live Integration Framework](live-integration-framework.md) - Decision framework for live sources
