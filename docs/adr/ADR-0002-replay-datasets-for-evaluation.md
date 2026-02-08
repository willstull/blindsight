# ADR-0002: Replay Datasets for Evaluation

## Status

Accepted

## Context

Evaluating an incident investigation system requires test scenarios with known outcomes. Real security incidents are unpredictable, sensitive, and non-reproducible. Waiting for live incidents would prevent systematic testing and development iteration.

The system must demonstrate correct behavior with both complete and degraded data to validate gap-aware confidence scoring.

## Decision

Use static replay datasets stored as NDJSON files with known investigation outcomes. Each scenario includes:
- Entities, events, and relationships in canonical format
- Coverage metadata indicating source availability
- Expected claims and hypotheses with confidence bounds
- Degraded variants with simulated gaps (missing sources, fields, retention windows)

All MCP adapter implementations must support a replay mode that reads from these fixtures before implementing live integrations.

## Rationale

- Deterministic testing: same inputs produce identical outputs
- Enables development without live system access
- Allows systematic testing of gap handling
- Supports regression detection via golden output comparison
- Scenarios can be version controlled and shared
- Reproducible evaluation for academic review

## Consequences

Positive:
- Can develop and test without live telemetry sources
- Systematic validation of gap-aware confidence scoring
- Regression testing via output comparison
- Scenarios document expected system behavior

Negative:
- Replay datasets may not capture all edge cases from live systems
- Requires manual creation of realistic scenarios
- Must maintain fixtures as ontology evolves
- Time normalization required for scenario timestamps
