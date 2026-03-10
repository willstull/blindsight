# Current Status

## Done

- Core ontology, identity contract, MCP patterns, normalized output spec, replay dataset contract, integration interface, ADRs
- Milestone 1: Replay-backed identity MCP server implemented
- Milestone 4: DuckDB case store implemented
  - Case store: open/create/migrate, case CRUD (src/services/case/store.py)
  - Ingest: entities, events, relationships, coverage, tool calls with upsert (src/services/case/ingest.py)
  - Query: entities, events, neighbors, timeline, tool history with JSON parsing (src/services/case/query.py)
  - Case MCP server: 9 tools, factory pattern, static coverage report (src/servers/case_mcp.py)
  - Schema: all 11 tables from case-store-schema.md (analysis tables created, tools deferred)
  - 115 tests passing (99 unit, 16 integration; 54 new case tests)

## Doing

None

## Blocked

None
