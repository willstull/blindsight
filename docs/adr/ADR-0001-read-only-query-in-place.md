# ADR-0001: Read-Only Query-in-Place Architecture

## Status

Accepted

## Context

Incident responders need access to telemetry across multiple systems (identity providers, cloud audit logs, application logs) during active investigations. Organizations already have logging and analytics infrastructure in place. The question is whether investigation tooling should duplicate this data or query it where it lives.

Existing systems already store the required telemetry with their own retention policies, access controls, and infrastructure.

## Decision

Blindsight will use read-only MCP integrations that query existing telemetry systems in-place and normalize results to normalized records. No continuous, organization-wide ingestion or indexing.

The system maintains a case-scoped evidence record:
- Tool calls executed (inputs/outputs, timestamps)
- Source references pointing to raw sources (URLs, query IDs, event IDs)
- Selected evidence artifacts (exports, snapshots, small log slices) for reproducibility
- Derived objects (entities, events, relationships)
- Claims, hypotheses, and coverage reports

Optional: Bounded caching of snapshots for determinism (scoped to a case, not general ingestion).

Blindsight sits on top of existing logging and analytics infrastructure, not as a replacement for it.

## Rationale

- Works with existing telemetry infrastructure (SIEM, log aggregators, cloud audit APIs)
- Respects existing retention policies and access controls
- Reduces attack surface (read-only operations)
- Enables rapid prototyping without data pipeline work
- Investigation layer on top of enterprise logging, not a replacement for it
- Avoids competing with or duplicating existing analytics platforms

## Consequences

Positive:
- Complements existing telemetry infrastructure rather than replacing it
- Lower infrastructure requirements (no duplicate storage)
- Faster time to working prototype
- Natural enforcement of read-only constraint
- Clear positioning: investigation tooling, not a logging platform

Negative:
- Query latency depends on source system performance
- No ability to query data after source retention expires
- Limited ability to optimize queries across sources
- Requires source systems to remain available during investigation
