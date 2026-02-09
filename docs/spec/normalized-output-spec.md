# Normalized Output Specification

> Single source of truth for all MCP tool responses

## Universal Response Envelope

**Every MCP tool** in every domain MUST return this structure:

```python
{
    "status": "success" | "partial" | "error",
    "domain": str,                          # Which domain generated this
    "coverage_report": CoverageReport,      # ALWAYS present (even if "unknown")

    # Data fields (tool-specific, optional based on status)
    "items": [...],                         # entities | events | relationships

    # Error tracking (optional, present if status != "success")
    "error": PipelineError,                 # Structured error
    "limitations": [str],                   # Human-readable limitations list

    # Pagination (optional)
    "next_page_token": str | null,          # null = last page

    # Correlation (always)
    "request_id": str                       # ULID for tracing
}
```

### Status Values

| Status | Meaning | When to Use |
|--------|---------|-------------|
| `success` | Operation completed, data is complete | coverage.overall_status == "complete" |
| `partial` | Operation completed, but data has gaps | coverage.overall_status == "partial" or "missing" |
| `error` | Operation failed | Any unrecoverable error |

**Key Rule**: If you have *some* data but *missing* sources/fields, use `"partial"` not `"error"`.

---

## Coverage Report (MANDATORY)

**Every response MUST include a coverage_report**, even if all fields are "unknown".

```python
{
    "id": str,                    # ULID
    "tlp": "RED" | "AMBER" | "AMBER_STRICT" | "GREEN" | "CLEAR",
    "domain": str,
    "time_range": {
        "start": str,             # RFC3339 timestamp
        "end": str
    },
    "overall_status": "complete" | "partial" | "missing" | "unknown",
    "sources": [
        {
            "source_name": str,
            "status": "complete" | "partial" | "missing" | "unknown"
        }
    ],
    "missing_fields": [str],      # Optional: list of unavailable fields
    "data_latency_seconds": int,  # Optional: ingestion lag
    "quality_flags": [str],       # Optional: ["retention_gap", "schema_drift"]
    "notes": str                  # Optional: human explanation
}
```

### Coverage Status Values

- **complete**: All data for this query is available
- **partial**: Some sources available, others missing/degraded
- **missing**: No data available (e.g., source offline, retention exceeded)
- **unknown**: Cannot determine coverage (initial state, configuration error)

### "Could Not Verify" Mechanism

When a tool **cannot answer** the question due to missing data:

```python
{
    "status": "partial",                    # Not "error"
    "domain": "identity",
    "items": [],                            # Empty results
    "limitations": [
        "Okta logs unavailable for requested time range",
        "AWS CloudTrail disabled",
        "Cannot verify: no credential change events found, but coverage incomplete"
    ],
    "coverage_report": {
        "overall_status": "missing",        # Explicit gap
        "sources": [
            {"source_name": "okta", "status": "missing"},
            {"source_name": "aws_iam", "status": "missing"}
        ],
        "notes": "Retention limit exceeded: logs only available for last 90 days"
    }
}
```

**Critical**: Downstream hypothesis scoring MUST use `coverage_report.overall_status` to cap confidence.

---

## Items Array (Data Payload)

All data objects in `items[]` follow normalized schemas from `ontology.yaml`:

### Entity
```python
{
    "id": str,                    # Normalized entity ID (within case)
    "tlp": str,
    "entity_type": "principal" | "credential" | "session" | ...,
    "kind": str,                  # Domain-specific subtype
    "display_name": str,
    "refs": [Ref],                # Pointers to external systems
    "attributes": {...},          # Flattened normalized fields
    "first_seen": str,            # Optional timestamp
    "last_seen": str,             # Optional timestamp
    "confidence": float           # Optional 0.0-1.0
}
```

### ActionEvent
```python
{
    "id": str,
    "tlp": str,
    "domain": str,
    "ts": str,                    # RFC3339 timestamp
    "action": str,                # Taxonomy string (e.g., "auth.login.succeeded")
    "actor": {
        "actor_entity_id": str
    },
    "targets": [
        {
            "target_entity_id": str,
            "role": str           # Optional: "primary", "secondary"
        }
    ],
    "outcome": "succeeded" | "failed" | "unknown",
    "context": {...},             # Normalized fields (source_ip, user_agent, ...)
    "related_entity_ids": [str],  # Optional: other relevant entities
    "raw_refs": [Ref],            # MUST include source references
    "ingested_at": str            # Optional: when event was collected
}
```

### Relationship
```python
{
    "id": str,
    "tlp": str,
    "domain": str,
    "relationship_type": str,     # "has_credential", "member_of", ...
    "from_entity_id": str,
    "to_entity_id": str,
    "first_seen": str,            # Optional
    "last_seen": str,             # Optional
    "evidence_refs": [Ref]        # Optional: supporting evidence
}
```

### Ref (Source Reference)
```python
{
    "ref_type": str,              # "event_id", "log_pointer", "user_id", "ticket_id"
    "system": str,                # "cloudtrail", "okta", "postgres_audit"
    "value": str,                 # External identifier
    "url": str,                   # Optional: direct link
    "observed_at": str            # Optional: timestamp
}
```

---

## Error Object (When status == "error")

```python
{
    "code": "source_unavailable" | "time_range_required" | "limit_exceeded" | ...,
    "message": str,               # Human-readable explanation
    "severity": "warning" | "error" | "fatal",
    "stage": str,                 # Which component failed
    "can_retry": bool,
    "retry_strategy": str,        # Optional: "exponential_backoff", "none"
    "context": {...}              # Optional: additional debug info
}
```

---

## Pagination Contract

### Request
```python
{
    "limit": int,                 # 1-2000, server may cap lower
    "page_token": str             # Optional: from previous response
}
```

### Response
```python
{
    "items": [...],               # Current page
    "next_page_token": str | null # null = last page
}
```

**Rules**:
- Tokens are opaque (base64-encoded offsets, cursors, etc.)
- Server controls actual page size (may ignore client limit)
- Clients MUST NOT parse tokens
- `null` token means no more pages

---

## Stable Field Names

These field names are **locked** and MUST be consistent across all tools:

| Field | Type | Meaning |
|-------|------|---------|
| `status` | str | success \| partial \| error |
| `domain` | str | Which domain generated this |
| `coverage_report` | object | Data availability report |
| `items` | array | Main data payload |
| `error` | object | Structured error (if failed) |
| `limitations` | array[str] | Human-readable gaps |
| `next_page_token` | str\|null | Pagination cursor |
| `request_id` | str | Correlation ULID |

**No synonyms**: Don't use `results` instead of `items`, or `errors` instead of `error`.

---

## Tool Response Examples

### Success (Complete Data)
```json
{
  "status": "success",
  "domain": "identity",
  "request_id": "01HZYYCRN0WX...",
  "items": [
    {
      "id": "evt_01",
      "action": "auth.login.succeeded",
      "actor": {"actor_entity_id": "principal_alice"},
      ...
    }
  ],
  "coverage_report": {
    "id": "cov_01",
    "overall_status": "complete",
    "sources": [
      {"source_name": "okta", "status": "complete"}
    ]
  }
}
```

### Partial (Some Gaps)
```json
{
  "status": "partial",
  "domain": "identity",
  "request_id": "01HZYYCRN0WX...",
  "items": [
    {"id": "evt_01", ...}
  ],
  "limitations": [
    "AWS CloudTrail unavailable for 2026-01-15 to 2026-01-20",
    "source_ip field missing from Okta logs"
  ],
  "coverage_report": {
    "id": "cov_01",
    "overall_status": "partial",
    "sources": [
      {"source_name": "okta", "status": "complete"},
      {"source_name": "aws_iam", "status": "missing"}
    ],
    "missing_fields": ["source_ip"],
    "notes": "CloudTrail logging disabled for this account during window"
  }
}
```

### Error (Failed Operation)
```json
{
  "status": "error",
  "domain": "identity",
  "request_id": "01HZYYCRN0WX...",
  "error": {
    "code": "time_range_required",
    "message": "time_range with start and end is required",
    "severity": "error",
    "stage": "validate_request",
    "can_retry": false
  },
  "coverage_report": {
    "id": "cov_01",
    "overall_status": "unknown",
    "sources": []
  }
}
```

### Unknown Coverage (Initial State)
```json
{
  "status": "success",
  "domain": "identity",
  "request_id": "01HZYYCRN0WX...",
  "items": [],
  "coverage_report": {
    "id": "cov_01",
    "overall_status": "unknown",
    "sources": [
      {"source_name": "identity_provider", "status": "unknown"}
    ],
    "notes": "No sources configured yet"
  }
}
```

---

## Hypothesis Confidence Limiting Rule

**Downstream scoring MUST apply this rule**:

```python
def compute_hypothesis_confidence(hypothesis, coverage_reports):
    """
    Confidence limit is determined by worst coverage status in evidence chain.
    """
    likelihood_score = compute_likelihood(hypothesis.claims)  # 0.0-1.0

    # Limit based on coverage
    confidence_limit = 1.0
    for cov in coverage_reports:
        if cov.overall_status == "complete":
            confidence_limit = min(confidence_limit, 1.0)
        elif cov.overall_status == "partial":
            confidence_limit = min(confidence_limit, 0.7)  # Reduced confidence
        elif cov.overall_status == "missing":
            confidence_limit = min(confidence_limit, 0.3)  # Very low confidence
        elif cov.overall_status == "unknown":
            confidence_limit = min(confidence_limit, 0.5)  # Medium confidence

    return {
        "likelihood_score": likelihood_score,
        "confidence_limit": confidence_limit,
        "final_confidence": min(likelihood_score, confidence_limit)  # Take minimum
    }
```

**Example**:
- Strong evidence → likelihood = 0.95
- But Okta logs missing → confidence_limit = 0.3
- **Final confidence = 0.3** (cannot be more certain than data allows)

---

## Summary: Normalized Output Contract

Every tool response MUST:
1. ✅ Include `status`, `domain`, `coverage_report`, `request_id`
2. ✅ Use "partial" status when data has gaps (not "error")
3. ✅ Include coverage_report even if "unknown"
4. ✅ Populate `limitations[]` with human-readable gap explanations
5. ✅ Use stable field names from this spec (no synonyms)
6. ✅ Follow normalized schemas from `ontology.yaml` for items
7. ✅ Include `raw_refs` for all ActionEvents (source references required)

This spec is the **single source of truth** for tool output structure.
