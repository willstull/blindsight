# ADR-0003: DuckDB as Case Record Store

## Status

Accepted

## Context

Investigation case records must be persisted and queryable. Each case needs:
- Tool-call history (inputs/outputs, timestamps)
- Pointers to raw sources (URLs, query IDs, event IDs)
- Selected evidence artifacts (exports, snapshots, small log slices)
- Derived objects (entities, events, relationships)
- Claims, hypotheses, and coverage reports

Storage requirements:
- Local storage without server infrastructure
- SQL query capability for correlation analysis
- JSON/structured data support
- Embedded deployment (no separate database server)

Scale: Single-user investigations, hundreds to low thousands of records per case, read-heavy workload.

## Decision

Use DuckDB as the embedded analytical database for case records. Each investigation case is a separate DuckDB file.

Store:
- Tool-call history (request/response pairs with timestamps)
- Source references pointing to raw sources (URLs, query IDs, event IDs)
- Selected evidence artifacts (exports, snapshots, small log slices)
- Normalized records (entities, events, relationships) in typed tables
- Claims and hypotheses with references to supporting evidence
- Coverage reports for gap tracking

## Rationale

- Embedded database (no server required)
- Excellent JSON support (native JSON type and path queries)
- Fast analytical queries on structured data
- Single-file database enables case archival
- SQL interface simplifies correlation queries
- Active development and good Python integration
- Suitable for investigation-scale data volumes

## Consequences

Positive:
- No database server to manage
- SQL enables flexible correlation queries
- Single file per case simplifies archival
- Fast enough for investigation workloads
- Good structured data support

Negative:
- Single-writer limitation (acceptable for single-user investigation flow)
- Overkill if only storing tool-call history
- Requires schema migration strategy as ontology evolves
- Not designed for concurrent multi-user access
