# Blindsight Roadmap

## Milestone 1: Replay-Backed Identity Server

**Outcome**: MCP server implementing identity domain tools using replay datasets. Server returns deterministic results for all query tools.

**Capabilities**:
- Discovery tools report domain capabilities and type schemas
- Query tools read from NDJSON fixtures and return normalized records
- All responses include coverage reports
- Response envelope matches tool contract specification
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
- Confidence limits applied when coverage incomplete
- Test suite validates coverage-aware scoring

**Validation**:
- All scenarios produce expected outcomes
- Degraded variants show reduced confidence limits
- Gap references link to coverage reports

## Milestone 3: Live Integration

**Outcome**: One live source integration (Okta, AWS CloudTrail, or Azure AD) implements domain integration interface and passes tool contract tests.

**Capabilities**:
- Integration implements DomainIntegration interface
- Real API queries return normalized records
- Coverage reports reflect actual source limitations
- Error handling for API failures and rate limits
- Authentication and authorization implemented

**Validation**:
- Tool contract tests pass with live integration
- Scripted scenario with known outcome succeeds
- Coverage reports accurately reflect source gaps

## Milestone 4: Case Record Storage

**Outcome**: Investigation results persist in DuckDB with tool-call history for reproducibility.

**Capabilities**:
- Normalized records stored in typed tables
- Claims and hypotheses with evidence references
- Tool-call history captures request/response pairs
- Coverage reports stored for gap tracking
- Query interface for case data

**Validation**:
- Stored objects can be queried and retrieved
- Tool-call history enables investigation replay
- Schema handles ontology types correctly

## Milestone 5: Investigation Orchestration Server

**Outcome**: MCP server that orchestrates identity + case servers to run bounded investigations. One `run_investigation` call produces a structured report with hypothesis, scores, and gaps.

**Capabilities**:
- Mechanical mode: deterministic scoring, no LLM, reproducible results
- LLM mode: same mechanical scores, LLM writes narrative text
- Per-investigation subprocess lifecycle (no cross-contamination)
- Scoring extracted into reusable service functions

**Validation**:
- Existing tests pass
- Server starts and accepts MCP connections
- describe_scenario returns manifest metadata
- run_investigation produces valid InvestigationReport matching demo_local.py scores
- No stdout leaks from subprocess servers
