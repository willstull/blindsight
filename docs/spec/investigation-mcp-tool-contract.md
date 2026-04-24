# Investigation MCP Server -- Tool Contracts

Tool contracts for the investigation orchestration MCP server (`src/blindsight/servers/investigation_mcp.py`).

## Response Categories

The investigation server exposes three categories of tools with different response shapes:

1. **Orchestration tools** (`run_investigation_tool`, `describe_scenario`): return investigation-native payloads.
2. **Case discovery** (`list_cases`): returns an investigation-native aggregate payload.
3. **Follow-up query tools** (`get_case_timeline`, `query_case_events`, `query_case_entities`, `query_case_neighbors`, `get_case_tool_call_history`): transparent proxies returning the case server's envelope unchanged. The envelope contains `status`, `domain: "case"`, `request_id`, `coverage_report`, plus tool-specific payload keys documented per tool below.
4. **Report generation** (`generate_report`): collects facts from the case store via MCP subprocess, renders a Markdown incident report with optional LLM prose.

See ADR-0008 for the rationale behind this design.

---

## run_investigation_tool

Run a bounded investigation against a replay scenario.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| scenario_name | string | yes | Scenario directory name or path |
| investigation_question | string | no | Override the manifest's default question |
| time_range_start | string | no | Override time range start (RFC3339) |
| time_range_end | string | no | Override time range end (RFC3339) |
| principal_hint | string | no | Hint for principal search query |
| max_tool_calls | integer | no | Budget for total MCP tool calls (default 30) |
| max_events | integer | no | Max events per search (default 2000) |
| use_llm | boolean | no | Use LLM for narrative text (default false) |
| llm_model | string | no | Model identifier for LLM mode |

**Success response:** `InvestigationReport` dict with keys: `scenario_name`, `investigation_question`, `hypothesis`, `likelihood` (low/medium/high), `confidence` (low/medium/high), `likelihood_rationale`, `confidence_rationale`, `gap_assessments`, `steps`, `case_id`, `tool_calls_used`, `total_events_evaluated`, etc.

**Error codes:** `scenario_not_found`

## describe_scenario

Describe a scenario, or list all available scenarios.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| scenario_name | string | no | Scenario to describe. If omitted, lists all. |

**Success response (single):** `{scenario_name, description, investigation_question, time_range, variant, tags}`

**Success response (list):** `{scenarios: [{name, description, variant}]}`

**Error codes:** `scenario_not_found` (includes `available` list)

---

## list_cases

List all cases discovered in the cases directory. Cases are discovered by globbing `*.duckdb` files on disk (survives server restarts).

**Parameters:** None.

**Success response:**
```json
{
  "cases": [
    {
      "case_id": "string",
      "title": "string",
      "status": "string",
      "severity": "string",
      "created_at": "string"
    }
  ]
}
```

If a case DB exists but metadata cannot be read, the entry contains only `{"case_id": "..."}`.

**Error codes:** None (returns empty list if no cases exist).

---

## get_case_timeline

Get chronological event timeline for a case. Proxies to the case server's `get_timeline_tool`.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |
| time_range_start | string | no | Filter events after this time (RFC3339) |
| time_range_end | string | no | Filter events before this time (RFC3339) |
| actor_entity_id | string | no | Filter events by actor |
| limit | integer | no | Max events to return (default 100) |

**Validation:** case_id must match `[a-zA-Z0-9_-]{1,128}`. Case DB must exist on disk.

**Success response:** Case server envelope with `events` key.

**Error codes:** `invalid_case_id`, `case_not_found`, plus any case server errors.

## query_case_events

Query events in a case with filters. Proxies to the case server's `query_events_tool`.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |
| actor_entity_id | string | no | Filter by actor entity |
| target_entity_id | string | no | Filter by target entity |
| actions | list[string] | no | Filter by action types |
| time_range_start | string | no | Filter events after this time (RFC3339) |
| time_range_end | string | no | Filter events before this time (RFC3339) |
| outcome | string | no | Filter by outcome (succeeded, failed, unknown) |
| limit | integer | no | Max events to return (default 100) |

**Validation:** case_id must match `[a-zA-Z0-9_-]{1,128}`. Case DB must exist on disk.

**Success response:** Case server envelope with `events` key.

**Error codes:** `invalid_case_id`, `case_not_found`, plus any case server errors.

## query_case_entities

Query entities in a case with filters. Proxies to the case server's `query_entities_tool`.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |
| entity_types | list[string] | no | Filter by entity type |
| kinds | list[string] | no | Filter by entity kind |
| display_name_contains | string | no | Substring match on display_name |
| limit | integer | no | Max entities to return (default 100) |

**Validation:** case_id must match `[a-zA-Z0-9_-]{1,128}`. Case DB must exist on disk.

**Success response:** Case server envelope with `entities` key.

**Error codes:** `invalid_case_id`, `case_not_found`, plus any case server errors.

## query_case_neighbors

Query entity neighbors via relationships in a case. Proxies to the case server's `query_neighbors_tool`.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |
| entity_id | string | yes | Entity to find neighbors for |
| relationship_types | list[string] | no | Filter by relationship types |
| limit | integer | no | Max neighbors to return (default 100) |

**Validation:** case_id must match `[a-zA-Z0-9_-]{1,128}`. Case DB must exist on disk.

**Success response:** Case server envelope with `entities` and `relationships` keys.

**Error codes:** `invalid_case_id`, `case_not_found`, plus any case server errors.

## get_case_tool_call_history

Get tool call audit history for a case. Proxies to the case server's `get_tool_call_history_tool`.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier |
| limit | integer | no | Max records to return (default 100) |

**Validation:** case_id must match `[a-zA-Z0-9_-]{1,128}`. Case DB must exist on disk.

**Success response:** Case server envelope with `results` key.

**Error codes:** `invalid_case_id`, `case_not_found`, plus any case server errors.

---

## generate_report

Generate a Markdown incident report from a completed investigation case. Collects facts from the case store, renders deterministic sections (NIST SP 800-61 Rev. 3 / CSF 2.0 aligned), and optionally generates LLM prose for human-readable sections.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| case_id | string | yes | Case identifier (must have a completed investigation) |
| use_llm | boolean | no | Use LLM for narrative prose sections (default false) |
| llm_model | string | no | Model identifier for LLM mode |

**Success response:**
```json
{
  "status": "success",
  "report": "# Incident Report: ...\n\n## 1. Executive Summary\n...",
  "facts_summary": {
    "case_id": "string",
    "scenario_name": "string",
    "likelihood": "low|medium|high",
    "confidence": "low|medium|high",
    "total_events": 42,
    "claims_count": 8,
    "evidence_items_count": 15,
    "timeline_events_count": 38,
    "transaction_count": 3,
    "transaction_total": 4500.00
  }
}
```

**Report sections:**
1. Executive Summary
2. Scope
3. Key Findings
4. Timeline
5. Evidence Assessment
6. Hypothesis Assessment
7. Impact and Exposure
8. Recommended Follow-Up
9. Reproducibility Appendix

**Error codes:** `invalid_case_id`, `case_not_found`, `no_facts`
