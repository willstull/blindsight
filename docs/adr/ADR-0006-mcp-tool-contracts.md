# ADR-0006: Shared MCP Tool Contracts Across Domains

## Status

Accepted

## Context

Each investigation domain (identity, network, cloud infrastructure, etc.) needs to expose query capabilities via MCP tools. Without shared conventions, each domain could develop incompatible interfaces, making cross-domain correlation difficult and forcing consumers to handle domain-specific patterns.

MCP tool responses must communicate both results and data quality (coverage, gaps, limitations).

## Decision

All domains implement a shared set of MCP tool patterns:

**Discovery Tools:**
- `describe_domain`: Return capabilities and current coverage status
- `describe_types`: Return entity types, relationship types, action taxonomies

**Query Tools:**
- `get_entity(entity_id)`: Fetch single entity by normalized ID
- `search_entities(query, filters)`: Free-text and filtered entity search
- `search_events(time_range, filters)`: Event search with time bounds
- `get_neighbors(entity_id, relationship_types, depth)`: Graph traversal
- `describe_coverage(time_range, scopes)`: Explicit gap reporting

**Universal Response Envelope:**
```
{
  "status": "success" | "partial" | "error",
  "domain": "<domain_name>",
  "coverage_report": { ... },  // ALWAYS present
  "items": [ ... ],
  "limitations": [ ... ],
  "next_page_token": str | null,
  "request_id": str
}
```

All tools return coverage reports even when status is "success" or "error".

## Rationale

- Consistent query patterns across domains reduce learning curve
- Universal response envelope simplifies cross-domain correlation
- Coverage reports enable confidence limiting via coverage tracking
- Shared tool contracts enable generic client code
- Tool naming conventions improve discoverability
- Status field distinguishes success, partial results, and errors

## Consequences

Positive:
- Domains are interchangeable from client perspective
- Cross-domain queries use identical patterns
- Coverage-aware clients work with all domains
- Shared validation and testing harness

Negative:
- May constrain domain-specific optimizations
- Lowest-common-denominator query interface
- Domains with unique capabilities require extensions
- Tool contract evolution affects all domains simultaneously
