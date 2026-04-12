# ADR-0010: Application Domain MCP Server

## Status

Accepted

## Context

ADR-0004 established domain-based architecture where each evidence domain (identity, network, cloud infrastructure, application) exposes the same MCP tool contract independently. The system had only one evidence domain (identity) implemented. Multi-domain correlation -- a core architectural claim -- was designed but unproven.

Seven replay scenarios already had app domain fixtures (entities, events, coverage) with placeholder coverage status ("No app domain server available for verification"). The investigation pipeline hardcoded identity-only orchestration.

## Decision

Add a second evidence domain: the application domain MCP server. It implements the same 7-tool contract (describe_domain, describe_types, get_entity, search_entities, search_events, get_neighbors, describe_coverage) using the shared replay infrastructure.

Key implementation choices:

1. **Shared replay base class**: `ReplayDomainIntegration` in `src/services/replay/` implements all 7 core contract methods generically. Both `ReplayIdentityIntegration` and `ReplayAppIntegration` inherit from it. Domain-specific convenience tools (resolve_principal, get_principal, list_credential_changes) stay on the identity MCP server, not the integration class.

2. **Conditional domain orchestration**: The investigation pipeline reads `manifest.domains` and launches the app MCP subprocess only when the manifest includes "app". Uses `AsyncExitStack` for clean optional session management.

3. **Minimal app pipeline calls**: Only `describe_coverage`, `search_events`, and `ingest_records` for the app domain. No separate `search_entities` or `get_neighbors` -- app `search_events` returns referenced entities, and identity already discovers principals.

4. **Event merging**: Identity events are partitioned (auth.login as background, rest as evidence). App events are all evidence. Both pools merge for scoring.

5. **Coverage merging**: A composite coverage envelope combines sources with domain-prefixed names (`identity:okta`, `app:app_audit`) and takes the worst overall_status. Domain-specific coverage is ingested into the case store separately.

6. **Entity merge on ingest**: When app and identity fixtures share entity IDs (e.g., principal_garcia_carlos), `ingest_entities()` merges refs and attributes instead of overwriting.

## Rationale

- Proves the multi-domain architecture works end-to-end, not just in design
- Same tool contract means no new MCP surface to learn
- Shared replay base class eliminates code duplication across domains
- The application domain adds evidence the identity domain cannot see: financial transactions, resource access, data operations
- Cross-domain correlation strengthens scoring: identity shows the manipulation, app shows what the manipulated account did

## Consequences

Positive:
- Multi-domain correlation is proven, not just claimed
- Future domains (network, cloud) follow the same pattern with minimal code
- Scoring pipeline sees richer evidence across domains
- Shared replay infrastructure reduces per-domain implementation effort

Negative:
- App subprocess adds ~1-2 seconds startup latency per multi-domain investigation
- Tool budget increased from 30 to 40 to accommodate app domain calls
- Focal principal selection may shift when app events change the activity distribution
- Entity merge behavior adds complexity to the ingest path
