# Case MCP Server -- Pivot Tool Contracts

Tool contracts for investigation pivot tools exposed by the case MCP server.

## save_investigation_pivot_tool

Save an investigation pivot -- a named evidence slice.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |
| label | string | yes | Pivot name (e.g. "evidence_search_result") |
| event_ids | list[string] | yes | Event IDs in this pivot |
| entity_ids | list[string] | yes | Entity IDs in this pivot |
| relationship_ids | list[string] | yes | Relationship IDs in this pivot |
| description | string | no | Human-readable description |
| focal_entity_ids | list[string] | no | Focal principal IDs |
| created_from_tool_call_ids | list[string] | no | Tool call IDs for audit trail |

**Validation:**
- case_id must match `[a-zA-Z0-9_-]{1,128}`
- Case DB must exist
- At least one of event_ids, entity_ids, or relationship_ids must be non-empty

**Success response:** `_success_envelope(request_id, results=[pivot_dict])`

**Error codes:** `invalid_case_id`, `case_not_found`, `db_open_failed`, `save_pivot_failed`

## list_investigation_pivots_tool

List all pivots for a case, ordered by creation time.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |

**Success response:** `_success_envelope(request_id, results=pivot_list)`

Each pivot includes computed `event_count`, `entity_count`, `relationship_count` fields.

**Error codes:** `invalid_case_id`, `case_not_found`, `db_open_failed`, `query_failed`

## get_investigation_pivot_tool

Fetch a single pivot by ID.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |
| pivot_id | string | yes | Pivot identifier |

**Success response:** `_success_envelope(request_id, results=[pivot_dict])`

**Error codes:** `invalid_case_id`, `case_not_found`, `db_open_failed`, `pivot_not_found`, `query_failed`

## query_pivot_timeline_tool

Get events belonging to a pivot, ordered chronologically (ascending).

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |
| pivot_id | string | yes | Pivot identifier |
| limit | integer | no | Max events to return (default 100) |

**Success response:** `_success_envelope(request_id, events=timeline_events)`

**Error codes:** `invalid_case_id`, `case_not_found`, `db_open_failed`, `query_failed`

## find_event_clusters_tool

Find temporal clusters of events within a pivot using sliding-window grouping.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |
| pivot_id | string | yes | Pivot identifier |
| window_minutes | integer | no | Max gap between events in a cluster (default 10) |
| min_events | integer | no | Minimum events to form a cluster (default 3) |

**Success response:** `_success_envelope(request_id, results=clusters)`

Each cluster contains:
- `cluster_id`: integer (0-indexed)
- `start`: timestamp of first event
- `end`: timestamp of last event
- `event_count`: number of events
- `event_ids`: list of event IDs
- `dominant_actions`: action types ordered by frequency

**Error codes:** `invalid_case_id`, `case_not_found`, `db_open_failed`, `query_failed`
