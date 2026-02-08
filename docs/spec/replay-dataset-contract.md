# Replay Dataset Contract

> Format for deterministic, repeatable investigation scenarios

## Purpose

Replay datasets enable **evaluation without real incidents**:
- Scripted scenarios with known outcomes
- Deterministic execution (same inputs → same outputs)
- Degraded variants (missing sources, fields, time windows)
- No dependency on live telemetry sources

## Replay Modes

Three modes of increasing scope. Choose based on what you need to prove.

### Mode A: Canonical Replay Fixtures (Lowest Scope)

**How you get canonical data**: You write it directly as NDJSON.

You author canonical ActionEvent/Entity/Relationship objects directly for each scenario and plane. No vendor logs, no normalization code.

**Files:** `entities.ndjson`, `events.ndjson`, `relationships.ndjson` contain canonical objects.

**What this tests:**
- Tool contract behavior (request → response shape)
- Coverage report generation logic
- Gap-aware hypothesis scoring (likelihood vs confidence cap)
- Case plane correlation queries
- Response envelope compliance

**What this does NOT test:**
- Raw-to-canonical normalization
- Vendor log parsing
- Field mapping from vendor schemas

**Pros:**
- Deterministic, fast
- Tests the contract, scoring, and case correlation
- No dependencies on vendor log formats

**Cons:**
- You are not proving vendor normalization works

**Recommendation:** Use Mode A for all 12 scenarios. This is sufficient to demonstrate the system.

---

### Mode B: Raw Replay Fixtures with Single Mapping (Bounded Raw Support)

**How you get canonical data**: Identity replay adapter reads raw export and normalizes it.

Pick one raw source format and support exactly that. Example: "Okta System Log JSONL export" or "CloudTrail JSON."

Evidence plane includes a `normalize(raw_record) -> ActionEvent + Entities + Relationships` function.

Replay dataset contains raw JSONL plus a mapping config.

**Files:**
- `raw/okta_system_log.jsonl` - Raw vendor logs
- `field_mappings.yaml` - How to map vendor fields to canonical fields
- `coverage.yaml` - Same as Mode A

**What this tests:**
- Normalization pipeline (raw → canonical)
- Vendor-specific field parsing
- Missing-field handling in raw logs
- Field mapping correctness

**What this does NOT test:**
- Live API quirks (rate limits, auth, pagination)
- Multiple vendor formats (only one supported)

**Pros:**
- Proves the real adapter work once
- Shows you can normalize vendor logs
- Still deterministic (no live API)

**Cons:**
- More time, more brittleness
- Only proves one vendor format

**Recommendation:** Add 1 Mode B scenario only if you need to demonstrate vendor normalization for writeup/demo.

---

### Mode C: Live Integration (Highest Scope)

**How you get canonical data**: Adapter queries live system and normalizes responses.

Evidence plane queries a real API (Okta, CloudTrail, Azure AD) and normalizes responses.

No replay fixtures - adapter makes real HTTP requests during test execution.

**What this tests:**
- Real API integration (auth, pagination, rate limits)
- Vendor-specific quirks and edge cases
- Network error handling
- End-to-end realism

**What this does NOT test (differently than Mode A/B)**:
- The architecture (already proven with replay)

**Pros:**
- Realistic
- Demonstrates production readiness

**Cons:**
- Auth, permissions, rate limits, tenant setup
- Testing headaches (flaky tests, cleanup, API costs)
- Requires external system availability

**Recommendation:** Optional. Defer until replay evaluation proves the system. Use for "Future Work" or stretch goal only.

---

## Directory Layout

```
tests/fixtures/replay/
├── scenarios/
│   ├── credential_change_baseline/
│   │   ├── manifest.yaml                    # Scenario metadata
│   │   ├── planes/
│   │   │   └── identity/
│   │   │       ├── entities.ndjson         # Entity catalog
│   │   │       ├── events.ndjson           # Event stream
│   │   │       ├── relationships.ndjson    # Relationship edges
│   │   │       └── coverage.yaml           # Coverage metadata
│   │   └── expected_output.json            # Golden output
│   │
│   ├── credential_change_degraded/
│   │   ├── manifest.yaml                    # Same scenario, degraded
│   │   ├── planes/
│   │   │   └── identity/
│   │   │       ├── entities.ndjson
│   │   │       ├── events.ndjson           # ← Fewer events (gap)
│   │   │       └── coverage.yaml           # ← overall_status: "partial"
│   │   └── expected_output.json            # ← Lower confidence cap
│   │
│   └── privilege_escalation_baseline/
│       └── ...
│
└── shared/
    └── time_normalization.yaml              # Time offset rules
```

---

## Manifest File (`manifest.yaml`)

**Required**: Every scenario has a manifest describing the test case.

```yaml
scenario_name: "credential_change_baseline"
version: "1.0"
description: "Baseline scenario: credential change with complete telemetry"

# Investigation Question (IQ)
investigation_question: "Did principal alice@example.com change credentials in January 2026?"

# Time bounds for scenario
time_range:
  start: "2026-01-01T00:00:00Z"
  end: "2026-01-31T23:59:59Z"

# Which planes are exercised
planes:
  - identity

# Expected outcome summary (for quick reference, not validation)
expected_outcome:
  hypothesis_count: 1
  claim_count: 1
  overall_confidence: "high"  # high | medium | low

# Degradation type (baseline | degraded)
variant: "baseline"

# Tags for test selection
tags:
  - credential_change
  - identity_plane
  - complete_coverage
```

---

## Canonical Fixtures (Mode A)

These files contain **already-normalized canonical objects**, not raw vendor logs.

### Entity Catalog (`entities.ndjson`)

**Format**: Newline-delimited JSON (one Entity per line)

```jsonl
{"id": "principal_alice", "tlp": "GREEN", "entity_type": "principal", "kind": "user", "display_name": "alice@example.com", "refs": [{"ref_type": "user_id", "system": "okta", "value": "00u123"}]}
{"id": "credential_alice_pw", "tlp": "GREEN", "entity_type": "credential", "kind": "password", "display_name": "alice password", "refs": [{"ref_type": "credential_id", "system": "okta", "value": "cred456"}]}
{"id": "session_01", "tlp": "GREEN", "entity_type": "session", "kind": "web_session", "display_name": "alice session 2026-01-15", "refs": [{"ref_type": "session_id", "system": "okta", "value": "sess789"}]}
```

**What this represents**: The output of a plane adapter's normalization process, not raw IdP records.

**Key Rules**:
- One JSON object per line (no array wrapper)
- `id` field is the canonical entity ID within the case
- `refs[]` provides pointers back to external system identifiers (traceability)
- All entities referenced by events MUST be in this file

---

### Event Stream (`events.ndjson`)

**Format**: Newline-delimited JSON (one ActionEvent per line, sorted by timestamp)

```jsonl
{"id": "evt_01", "tlp": "GREEN", "plane": "identity", "ts": "2026-01-15T10:30:00Z", "action": "credential.update", "actor": {"actor_entity_id": "principal_alice"}, "targets": [{"target_entity_id": "credential_alice_pw"}], "outcome": "succeeded", "context": {"source_ip": "192.168.1.10", "user_agent": "Mozilla/5.0"}, "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "evt_okta_001"}]}
{"id": "evt_02", "tlp": "GREEN", "plane": "identity", "ts": "2026-01-15T10:35:00Z", "action": "auth.login.succeeded", "actor": {"actor_entity_id": "principal_alice"}, "targets": [{"target_entity_id": "session_01"}], "outcome": "succeeded", "context": {"source_ip": "192.168.1.10"}, "raw_refs": [{"ref_type": "event_id", "system": "okta", "value": "evt_okta_002"}]}
```

**What this represents**: Canonical ActionEvents already normalized from vendor logs.

**Key Rules**:
- Events MUST be sorted by `ts` ascending
- `actor.actor_entity_id` and `targets[].target_entity_id` MUST reference entities in `entities.ndjson`
- `raw_refs[]` is REQUIRED (provenance - points to hypothetical raw log entries)
- All timestamps MUST be within manifest `time_range`

---

## Relationships (`relationships.ndjson`)

**Format**: Newline-delimited JSON (one relationship per line)

```jsonl
{"id": "rel_01", "tlp": "GREEN", "plane": "identity", "relationship_type": "has_credential", "from_entity_id": "principal_alice", "to_entity_id": "credential_alice_pw", "first_seen": "2026-01-01T00:00:00Z"}
{"id": "rel_02", "tlp": "GREEN", "plane": "identity", "relationship_type": "authenticated_as", "from_entity_id": "session_01", "to_entity_id": "principal_alice", "first_seen": "2026-01-15T10:35:00Z"}
```

**Key Rules**:
- `from_entity_id` and `to_entity_id` MUST reference entities in `entities.ndjson`
- Relationships are directional (from → to)

---

## Coverage Metadata (`coverage.yaml`)

**Required**: Describes data availability for this scenario.

```yaml
plane: identity
overall_status: complete  # complete | partial | missing | unknown

sources:
  - source_name: okta
    status: complete
    available_fields: [id, ts, action, actor, targets, outcome, source_ip, user_agent]
    missing_fields: []

  - source_name: aws_iam
    status: complete
    available_fields: [id, ts, action, actor, targets, outcome]
    missing_fields: []

# Optional: data quality notes
data_latency_seconds: 0  # Replay is instant
quality_flags: []
notes: "Baseline scenario with complete telemetry from all sources"
```

**Degraded Variant Example**:
```yaml
plane: identity
overall_status: partial  # ← Degraded

sources:
  - source_name: okta
    status: complete
    available_fields: [id, ts, action, actor, targets, outcome]
    missing_fields: [source_ip, user_agent]  # ← Missing fields

  - source_name: aws_iam
    status: missing  # ← Entire source unavailable
    available_fields: []
    missing_fields: []

notes: "Degraded: AWS IAM CloudTrail disabled, Okta missing network context"
```

---

## Expected Output (`expected_output.json`)

**Golden file**: Deterministic output that investigation MUST produce.

```json
{
  "case_id": "case_test_001",
  "investigation_question": "Did principal alice@example.com change credentials in January 2026?",

  "claims": [
    {
      "id": "claim_01",
      "tlp": "GREEN",
      "statement": "alice@example.com updated credential on 2026-01-15T10:30:00Z",
      "polarity": "supports",
      "confidence": 0.95,
      "backed_by_evidence_ids": ["evt_01"],
      "subject_entity_ids": ["principal_alice", "credential_alice_pw"]
    }
  ],

  "hypotheses": [
    {
      "id": "hyp_01",
      "tlp": "GREEN",
      "iq_id": "iq_credential_change",
      "statement": "alice@example.com changed credentials during investigation window",
      "likelihood_score": 0.95,
      "confidence_cap": 1.0,
      "supporting_claim_ids": ["claim_01"],
      "contradicting_claim_ids": [],
      "gaps": [],
      "next_evidence_requests": [],
      "status": "ruled_in"
    }
  ],

  "coverage_summary": {
    "overall_status": "complete",
    "planes": {
      "identity": "complete"
    }
  }
}
```

**Degraded Variant Expected Output**:
```json
{
  "hypotheses": [
    {
      "id": "hyp_01",
      "statement": "alice@example.com changed credentials during investigation window",
      "likelihood_score": 0.5,    // ← Neutral (no evidence)
      "confidence_cap": 0.3,      // ← Low cap due to gaps
      "supporting_claim_ids": [],
      "gaps": ["cov_identity_01"],
      "status": "open"            // ← Cannot rule in/out
    }
  ],
  "coverage_summary": {
    "overall_status": "partial",  // ← Degraded
    "planes": {
      "identity": "partial"
    }
  }
}
```

---

## Query Mapping (How Queries Read Replay Data)

### Tool: `search_events`

**Request**:
```python
{
    "time_range": {"start": "2026-01-15T00:00:00Z", "end": "2026-01-16T00:00:00Z"},
    "actions": ["credential.update"],
    "limit": 100
}
```

**Replay Logic**:
```python
# Load events from events.ndjson
events = load_ndjson("planes/identity/events.ndjson")

# Filter by time range
filtered = [
    e for e in events
    if start <= parse_timestamp(e["ts"]) <= end
]

# Filter by actions (if specified)
if actions:
    filtered = [e for e in filtered if e["action"] in actions]

# Apply limit
filtered = filtered[:limit]

# Load coverage metadata
coverage = load_yaml("planes/identity/coverage.yaml")

# Return response
return {
    "status": "success" if coverage["overall_status"] == "complete" else "partial",
    "plane": "identity",
    "items": filtered,
    "coverage_report": build_coverage_report(coverage, time_range)
}
```

### Tool: `get_entity`

**Request**:
```python
{"entity_id": "principal_alice"}
```

**Replay Logic**:
```python
# Load entities from entities.ndjson
entities = load_ndjson("planes/identity/entities.ndjson")

# Find by ID
entity = next((e for e in entities if e["id"] == entity_id), None)

if not entity:
    return {"status": "error", "error": {"code": "entity_not_found"}}

# Load coverage
coverage = load_yaml("planes/identity/coverage.yaml")

return {
    "status": "success",
    "plane": "identity",
    "items": [entity],
    "coverage_report": build_coverage_report(coverage, None)
}
```

### Tool: `get_neighbors`

**Request**:
```python
{"entity_id": "principal_alice", "depth": 1}
```

**Replay Logic**:
```python
# Load relationships
relationships = load_ndjson("planes/identity/relationships.ndjson")

# Find edges from entity
edges = [r for r in relationships if r["from_entity_id"] == entity_id]

# Load referenced entities
entities = load_ndjson("planes/identity/entities.ndjson")
neighbor_ids = [e["to_entity_id"] for e in edges]
neighbors = [e for e in entities if e["id"] in neighbor_ids]

return {
    "status": "success",
    "plane": "identity",
    "entities": neighbors,
    "relationships": edges,
    "coverage_report": ...
}
```

---

## Time Normalization Rules

**Problem**: Test execution time differs from scenario time.

**Solution**: Offset timestamps to "now" during replay.

```yaml
# tests/fixtures/replay/shared/time_normalization.yaml
scenarios:
  credential_change_baseline:
    # Scenario defines time range 2026-01-01 to 2026-01-31
    # Tests run in 2026-02-07
    # Offset all timestamps by: test_time - scenario_end
    offset_mode: "relative"  # or "absolute"
    anchor: "end"            # Align scenario end with test execution time
```

**Normalization Logic**:
```python
def normalize_timestamp(scenario_ts: str, scenario_end: str, test_now: str) -> str:
    """Shift scenario timestamps to align with test execution time"""
    offset = parse(test_now) - parse(scenario_end)
    normalized = parse(scenario_ts) + offset
    return normalized.isoformat()
```

---

## Degraded Variant Rules

### 1. Missing Source Variant
- **Change**: Remove source from `coverage.yaml`, set status: "missing"
- **Effect**: No events from that source in `events.ndjson`
- **Expected**: Lower confidence cap in `expected_output.json`

### 2. Missing Fields Variant
- **Change**: Remove fields from events (e.g., delete `source_ip` from all events)
- **Effect**: `missing_fields: [source_ip]` in `coverage.yaml`
- **Expected**: Claims note limited context, confidence reduced

### 3. Retention Gap Variant
- **Change**: Remove events outside time window
- **Effect**: `coverage.yaml` notes: "Retention limited to 90 days"
- **Expected**: Hypothesis includes `gaps: [...]`, confidence capped

### 4. Ingestion Delay Variant
- **Change**: Set `data_latency_seconds: 7200` in `coverage.yaml`
- **Effect**: Recent events (< 2 hours ago) missing from `events.ndjson`
- **Expected**: Coverage report notes delay, confidence cap if critical window affected

---

## Test Execution Flow

```python
@pytest.mark.asyncio
async def test_scenario_replay(scenario_name: str):
    """Run replay scenario and validate against golden output"""

    # 1. Load scenario
    manifest = load_yaml(f"scenarios/{scenario_name}/manifest.yaml")
    expected = load_json(f"scenarios/{scenario_name}/expected_output.json")

    # 2. Create replay-backed plane adapters
    identity_adapter = ReplayIdentityPlane(
        data_dir=f"scenarios/{scenario_name}/planes/identity"
    )

    # 3. Run investigation
    result = await run_investigation(
        question=manifest["investigation_question"],
        time_range=manifest["time_range"],
        planes={"identity": identity_adapter}
    )

    # 4. Assert exact match with golden output
    assert result.claims == expected["claims"]
    assert result.hypotheses == expected["hypotheses"]
    assert result.coverage_summary == expected["coverage_summary"]
```

---

## Summary: Replay Dataset Contract

**Directory Structure**:
- `scenarios/{name}/manifest.yaml` - Scenario metadata
- `scenarios/{name}/planes/{plane}/{entities|events|relationships}.ndjson` - Data
- `scenarios/{name}/planes/{plane}/coverage.yaml` - Availability metadata
- `scenarios/{name}/expected_output.json` - Golden output

**Key Principles**:
1. ✅ Deterministic: Same inputs → same outputs
2. ✅ Self-contained: No external dependencies
3. ✅ Degraded variants: Test missing-data behavior
4. ✅ Golden outputs: Exact comparison for regression detection
5. ✅ Coverage-aware: Every scenario defines data availability

This contract makes "no live incidents required" evaluation defensible.

---

## Mode B Example: Raw Replay Directory Structure

If implementing Mode B for one scenario:

```
scenarios/credential_change_raw/
├── manifest.yaml
├── planes/
│   └── identity/
│       ├── raw/
│       │   └── okta_system_log.jsonl    # Raw vendor logs
│       ├── field_mappings.yaml          # Normalization rules
│       └── coverage.yaml
└── expected_output.json
```

**Example Raw Log** (`okta_system_log.jsonl`):
```jsonl
{"uuid":"evt_okta_001","published":"2026-01-15T10:30:00.000Z","eventType":"user.account.update_password","actor":{"id":"00u123","type":"User","alternateId":"alice@example.com"},"target":[{"id":"cred456","type":"Password"}],"outcome":{"result":"SUCCESS"},"client":{"ipAddress":"192.168.1.10","userAgent":{"rawUserAgent":"Mozilla/5.0"}}}
```

**Field Mappings** (`field_mappings.yaml`):
```yaml
vendor: "okta"
version: "1.0"

mappings:
  entity:
    principal:
      id_path: "actor.id"
      display_name_path: "actor.alternateId"
      kind: "user"

  event:
    id_path: "uuid"
    ts_path: "published"
    action_path: "eventType"
    action_mappings:
      "user.account.update_password": "credential.update"
      "user.session.start": "auth.login.succeeded"
    actor_entity_id_path: "actor.id"
    outcome_path: "outcome.result"
    outcome_mappings:
      "SUCCESS": "succeeded"
      "FAILURE": "failed"
    context:
      source_ip_path: "client.ipAddress"
      user_agent_path: "client.userAgent.rawUserAgent"
```

**Normalization Function** (`services/identity/normalize.py`):
```python
def normalize_okta_event(raw_event: dict, mappings: dict) -> Tuple[ActionEvent, List[Entity]]:
    """Convert raw Okta log to canonical ActionEvent + Entities"""
    # Implementation reads field_mappings.yaml and applies transforms
    pass
```

**Use Case**: Add 1 Mode B scenario if writeup/demo needs to show vendor normalization works.
