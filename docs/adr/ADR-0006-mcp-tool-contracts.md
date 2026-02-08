# ADR-0006: Shared MCP Tool Contracts Across Planes

## Status

Accepted

## Context

Each investigation plane (identity, network, resource) needs to expose query capabilities via MCP tools. Without shared conventions, each plane could develop incompatible interfaces, making cross-plane correlation difficult and forcing consumers to handle plane-specific patterns.

MCP tool responses must communicate both results and data quality (coverage, gaps, limitations).

## Decision

All planes implement a shared set of MCP tool patterns:

**Discovery Tools:**
- `describe_plane`: Return capabilities and current coverage status
- `describe_types`: Return entity types, relationship types, action taxonomies

**Query Tools:**
- `get_entity(entity_id)`: Fetch single entity by canonical ID
- `search_entities(query, filters)`: Free-text and filtered entity search
- `search_events(time_range, filters)`: Event search with time bounds
- `get_neighbors(entity_id, relationship_types, depth)`: Graph traversal
- `describe_coverage(time_range, scopes)`: Explicit gap reporting

**Universal Response Envelope:**
```
{
  "status": "success" | "partial" | "error",
  "plane": "<plane_name>",
  "coverage_report": { ... },  // ALWAYS present
  "items": [ ... ],
  "limitations": [ ... ],
  "next_page_token": str | null,
  "request_id": str
}
```

All tools return coverage reports even when status is "success" or "error".

## Rationale

- Consistent query patterns across planes reduce learning curve
- Universal response envelope simplifies cross-plane correlation
- Coverage reports enable gap-aware scoring
- Shared contracts enable generic client code
- Tool naming conventions improve discoverability
- Status field distinguishes success, partial results, and errors

## Consequences

Positive:
- Planes are interchangeable from client perspective
- Cross-plane queries use identical patterns
- Coverage-aware clients work with all planes
- Shared validation and testing harness

Negative:
- May constrain plane-specific optimizations
- Lowest-common-denominator query interface
- Planes with unique capabilities require extensions
- Contract evolution affects all planes simultaneously
