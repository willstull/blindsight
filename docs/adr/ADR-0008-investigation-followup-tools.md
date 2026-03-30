# ADR-0008: Investigation Follow-up Query Tools

## Status

Accepted (supersedes ADR-0007 point 4)

## Context

After an investigation completes via `run_investigation_tool`, the case data (events, entities, relationships, tool call audit history) lives in a DuckDB file under a stable cases directory. Users cannot query this data without manually launching a case MCP server pointed at the correct directory path. The investigation server is the only MCP surface that knows where cases live.

ADR-0007 point 4 defined the investigation server's tool surface as two tools: `run_investigation` and `describe_scenario`. This was appropriate when the server was purely an orchestration entrypoint. With persisted case data, users need a way to explore investigation results without leaving the investigation server context.

## Decision

Expand the investigation server from 2 tools to 8 tools by adding 6 follow-up query tools that proxy to case MCP subprocesses:

- `list_cases` -- discovers case DBs from the filesystem, returns metadata
- `get_case_timeline` -- proxies to `get_timeline_tool`
- `query_case_events` -- proxies to `query_events_tool`
- `query_case_entities` -- proxies to `query_entities_tool`
- `query_case_neighbors` -- proxies to `query_neighbors_tool`
- `get_case_tool_call_history` -- proxies to `get_tool_call_history_tool`

Key design choices:

1. **MCP subprocess proxying preserved**: Follow-up tools use the same `open_mcp_session` / `call_tool` pattern as `run_investigation`. The investigation server does not import case service internals. ADR-0007 points 1-3, 5-6 remain unchanged.

2. **Filesystem-backed discovery, no in-memory registry**: Case existence is determined by globbing `*.duckdb` files in the cases directory. No in-memory state required. Discovery survives server restarts and finds cases created by previous sessions.

3. **Stable cases directory**: The investigation server uses a persistent `cases_dir` (defaulting to `.blindsight_cases/` or `$BLINDSIGHT_CASES_DIR`) instead of per-run temp directories. This is passed through to `run_investigation` so case DBs accumulate in one location.

4. **Three response categories**: Orchestration tools return investigation-native payloads. `list_cases` returns an investigation-native aggregate. The 5 query tools return the case server's `_success_envelope` unchanged (transparent proxy).

## Rationale

- The investigation server already manages case lifecycle (creates cases, writes evidence, saves pivots). Exposing read-back is a natural extension of that responsibility.
- Subprocess proxying preserves ADR-0007's boundary discipline -- no architectural regression.
- Filesystem-backed discovery avoids the fragility of in-memory registries that lose state on restart.
- The alternative (requiring users to launch a separate case MCP server with the correct path) forces knowledge of internal file layout onto external clients.

## Consequences

- Investigation server tool surface grows from 2 to 8. The server's role broadens from "orchestrator entrypoint" to "orchestrator plus post-investigation case-query facade."
- Each follow-up call incurs subprocess startup overhead (case MCP server launch). Acceptable for interactive query workloads.
- The server now has a stable `cases_dir`, which is a new operational concern (disk usage, cleanup policy).
- ADR-0007 point 4 is superseded. That ADR is not edited; this ADR records the change.
- Clients must handle two response shapes: investigation-native (from orchestration tools) and case-envelope (from query tools). The spec documents this explicitly.
