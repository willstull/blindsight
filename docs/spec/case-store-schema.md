# Case Store Schema (DuckDB)

This document defines the database schema for case record persistence.

## Tables

### entities

Canonical entity records ingested from evidence planes.

```sql
CREATE TABLE entities (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    entity_type VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    refs JSON,                      -- Array of Ref objects
    attributes JSON,                 -- Flattened key-value pairs
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    confidence DOUBLE,
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_entities_type_kind ON entities(entity_type, kind);
CREATE INDEX idx_entities_display_name ON entities(display_name);
```

### events

Canonical action events ingested from evidence planes.

```sql
CREATE TABLE events (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    plane VARCHAR NOT NULL,
    ts TIMESTAMP NOT NULL,
    action VARCHAR NOT NULL,
    actor JSON NOT NULL,            -- Actor object {actor_entity_id: str}
    targets JSON NOT NULL,          -- Array of Target objects [{target_entity_id: str, role: str}]
    outcome VARCHAR NOT NULL,       -- 'succeeded', 'failed', 'unknown'
    raw_refs JSON NOT NULL,         -- Array of Ref objects (provenance)
    context JSON,                    -- Normalized context fields
    related_entity_ids JSON,         -- Array of entity IDs
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_events_ts ON events(ts);
CREATE INDEX idx_events_plane_action ON events(plane, action);
CREATE INDEX idx_events_actor ON events((json_extract_string(actor, '$.actor_entity_id')));
```

### relationships

Typed edges between entities.

```sql
CREATE TABLE relationships (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    plane VARCHAR NOT NULL,
    relationship_type VARCHAR NOT NULL,
    from_entity_id VARCHAR NOT NULL,
    to_entity_id VARCHAR NOT NULL,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    evidence_refs JSON,              -- Array of Ref objects
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (from_entity_id) REFERENCES entities(id),
    FOREIGN KEY (to_entity_id) REFERENCES entities(id)
);

CREATE INDEX idx_relationships_from ON relationships(from_entity_id);
CREATE INDEX idx_relationships_to ON relationships(to_entity_id);
CREATE INDEX idx_relationships_type ON relationships(relationship_type);
```

### coverage_reports

Machine-readable visibility and gap tracking.

```sql
CREATE TABLE coverage_reports (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    plane VARCHAR NOT NULL,
    time_range_start TIMESTAMP NOT NULL,
    time_range_end TIMESTAMP NOT NULL,
    overall_status VARCHAR NOT NULL,  -- 'complete', 'partial', 'missing', 'unknown'
    sources JSON NOT NULL,             -- Array of {source_name: str, status: str}
    missing_fields JSON,               -- Array of field names
    data_latency_seconds DOUBLE,
    quality_flags JSON,                -- Array of strings
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_coverage_plane_time ON coverage_reports(plane, time_range_start, time_range_end);
```

### evidence_items

Analytic wrapper pointing to raw sources.

```sql
CREATE TABLE evidence_items (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    plane VARCHAR NOT NULL,
    summary TEXT NOT NULL,
    raw_refs JSON NOT NULL,           -- Array of Ref objects (provenance)
    collected_at TIMESTAMP NOT NULL,
    related_entity_ids JSON,           -- Array of entity IDs
    related_event_ids JSON,            -- Array of event IDs
    hash VARCHAR,                      -- Content hash for deduplication
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_evidence_plane ON evidence_items(plane);
CREATE INDEX idx_evidence_collected ON evidence_items(collected_at);
```

### claims

Atomic analytic statements backed by evidence.

```sql
CREATE TABLE claims (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    statement TEXT NOT NULL,
    polarity VARCHAR NOT NULL,        -- 'supports', 'contradicts', 'neutral'
    confidence DOUBLE NOT NULL,       -- 0.0 to 1.0
    backed_by_evidence_ids JSON NOT NULL,  -- Array of evidence_item IDs
    subject_entity_ids JSON,           -- Array of entity IDs
    time_range_start TIMESTAMP,
    time_range_end TIMESTAMP,
    derived_from_claim_ids JSON,       -- Array of claim IDs
    assumption_ids JSON,               -- Array of assumption IDs
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_claims_confidence ON claims(confidence);
CREATE INDEX idx_claims_polarity ON claims(polarity);
```

### assumptions

Explicit assumptions with strength tracking.

```sql
CREATE TABLE assumptions (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    statement TEXT NOT NULL,
    strength VARCHAR NOT NULL,        -- 'solid', 'caveated', 'unsupported'
    rationale TEXT NOT NULL,
    impacts JSON,                      -- Array of impact descriptions
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### hypotheses

Structured hypotheses with gap-aware confidence.

```sql
CREATE TABLE hypotheses (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    iq_id VARCHAR NOT NULL,           -- Investigation question ID
    statement TEXT NOT NULL,
    likelihood_score DOUBLE NOT NULL, -- 0.0 to 1.0 (what evidence suggests)
    confidence_cap DOUBLE NOT NULL,   -- 0.0 to 1.0 (upper bound due to gaps)
    supporting_claim_ids JSON NOT NULL,  -- Array of claim IDs
    contradicting_claim_ids JSON,      -- Array of claim IDs
    gaps JSON NOT NULL,                -- Array of coverage_report IDs
    next_evidence_requests JSON NOT NULL,  -- Array of {plane, tool, params, priority}
    status VARCHAR,                    -- 'open', 'ruled_in', 'ruled_out', 'stale'
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_hypotheses_iq ON hypotheses(iq_id);
CREATE INDEX idx_hypotheses_status ON hypotheses(status);
```

### cases

Minimal case tracking.

```sql
CREATE TABLE cases (
    id VARCHAR PRIMARY KEY,
    tlp VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    status VARCHAR NOT NULL,          -- 'new', 'investigating', 'contained', 'resolved', 'closed'
    severity VARCHAR NOT NULL,        -- 'sev0', 'sev1', 'sev2', 'sev3', 'sev4'
    created_at TIMESTAMP NOT NULL,
    detected_at TIMESTAMP,
    contained_at TIMESTAMP,
    resolved_at TIMESTAMP,
    mttd_seconds DOUBLE,              -- Mean time to detect
    mttc_seconds DOUBLE,              -- Mean time to contain
    mttr_seconds DOUBLE,              -- Mean time to resolve
    hypothesis_ids JSON,               -- Array of hypothesis IDs
    tags JSON,                         -- Array of tag strings
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cases_status ON cases(status);
CREATE INDEX idx_cases_severity ON cases(severity);
```

### tool_calls

Tool-call history for reproducibility.

```sql
CREATE TABLE tool_calls (
    id VARCHAR PRIMARY KEY,
    case_id VARCHAR NOT NULL,
    request_id VARCHAR NOT NULL,      -- ULID for correlation
    plane VARCHAR NOT NULL,
    tool_name VARCHAR NOT NULL,
    request_params JSON NOT NULL,
    response_status VARCHAR NOT NULL, -- 'success', 'partial', 'error'
    response_body JSON NOT NULL,
    coverage_report_id VARCHAR,       -- FK to coverage_reports
    executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    duration_ms INTEGER,
    FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE INDEX idx_tool_calls_case ON tool_calls(case_id);
CREATE INDEX idx_tool_calls_request ON tool_calls(request_id);
CREATE INDEX idx_tool_calls_executed ON tool_calls(executed_at);
```

## Correlation Query Examples

### Get entity neighbors via relationships

```sql
SELECT e.*, r.relationship_type
FROM entities e
JOIN relationships r ON (
    (r.to_entity_id = e.id AND r.from_entity_id = ?)
    OR (r.from_entity_id = e.id AND r.to_entity_id = ?)
)
WHERE r.relationship_type IN (?, ?, ...)
```

### Get events by actor

```sql
SELECT *
FROM events
WHERE json_extract_string(actor, '$.actor_entity_id') = ?
  AND ts BETWEEN ? AND ?
ORDER BY ts DESC
```

### Get events targeting entity

```sql
SELECT e.*
FROM events e,
     json_each(e.targets) AS t
WHERE json_extract_string(t.value, '$.target_entity_id') = ?
  AND e.ts BETWEEN ? AND ?
ORDER BY e.ts DESC
```

### Get claims supporting hypothesis

```sql
SELECT c.*
FROM claims c,
     json_each(?) AS h_claim_id
WHERE c.id = h_claim_id.value
ORDER BY c.confidence DESC
```

## Migration Strategy

Each table should have a corresponding migration script. Schema changes tracked via version table:

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    description VARCHAR NOT NULL,
    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

## Notes

- All JSON fields use DuckDB's native JSON type (efficient storage and querying)
- JSON extraction uses `json_extract_string()` for scalar values
- `json_each()` expands JSON arrays for joins
- Indexes on JSON paths require function-based indexes
- Foreign keys enforce referential integrity but allow orphaned records (investigation may be incomplete)
- All timestamps use UTC
- ULID used for IDs (time-sortable, globally unique)
