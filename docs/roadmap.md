# Blindsight Roadmap

## Milestone 1: Replay-Backed Identity Server

**Outcome**: MCP server implementing identity plane tools using replay datasets. Server returns deterministic results for all query tools.

**Capabilities**:
- Discovery tools report plane capabilities and type schemas
- Query tools read from NDJSON fixtures and return canonical objects
- All responses include coverage reports
- Response envelope matches contract specification
- Replay scenarios run deterministically

**Validation**:
- Contract compliance tests pass
- Golden output comparison detects regressions
- Multiple runs produce identical results

## Milestone 2: Evaluation Harness

**Outcome**: Replay scenarios with known investigation outcomes demonstrate correct behavior with complete and degraded data.

**Capabilities**:
- 3+ baseline scenarios with complete coverage
- 3+ degraded variants with simulated gaps
- Expected claims and hypotheses documented
- Confidence caps applied when coverage incomplete
- Test suite validates gap-aware scoring

**Validation**:
- All scenarios produce expected outcomes
- Degraded variants show reduced confidence bounds
- Gap references link to coverage reports

## Milestone 3: Live Integration

**Outcome**: One live source adapter (Okta, AWS CloudTrail, or Azure AD) implements plane interface and passes contract tests.

**Capabilities**:
- Adapter implements PlaneAdapter interface
- Real API queries return canonical objects
- Coverage reports reflect actual source limitations
- Error handling for API failures and rate limits
- Authentication and authorization implemented

**Validation**:
- Contract tests pass with live adapter
- Scripted scenario with known outcome succeeds
- Coverage reports accurately reflect source gaps

## Milestone 4: Case Record Storage

**Outcome**: Investigation results persist in DuckDB with tool-call history for reproducibility.

**Capabilities**:
- Canonical objects stored in typed tables
- Claims and hypotheses with evidence references
- Tool-call history captures request/response pairs
- Coverage reports stored for gap tracking
- Query interface for case data

**Validation**:
- Stored objects can be queried and retrieved
- Tool-call history enables investigation replay
- Schema handles ontology types correctly
