# Blindsight Documentation

## Specifications

Stable interfaces and invariants:

- [Ontology](spec/ontology.yaml) - Core domain-agnostic data model
- [Identity Domain Contract](spec/identity-domain-contract.json) - MCP tool specifications
- [Normalized Output Specification](spec/normalized-output-spec.md) - Universal response envelope
- [Replay Dataset Contract](spec/replay-dataset-contract.md) - Replay dataset format
- [Integration Interface](spec/integration-interface.md) - Domain integration boundary
- [Case Store Schema](spec/case-store-schema.md) - DuckDB tables
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
- [ADR-0009: Categorical Scoring](adr/ADR-0009-categorical-scoring.md)
- [ADR-0010: Application Domain Server](adr/ADR-0010-app-domain-server.md)
- [ADR-0011: Incident Report Generation](adr/ADR-0011-incident-report-generation.md)

## Reference

- [Appendix](appendix.md) - Terms and definitions
