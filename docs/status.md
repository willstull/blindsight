# Current Status

## Done

- Core ontology, identity contract, MCP patterns, normalized output spec, replay dataset contract, integration interface, ADRs 1-6
- Milestone 1: Replay-backed identity MCP server (10 tools, factory pattern, replay integration)
- Milestone 4: DuckDB case store (14 tools, 12 tables, ingest with upsert, correlation queries, pivot CRUD/timeline/clustering)
- Analytic types: EvidenceItem, Claim, Hypothesis, Assumption in core types; ingest functions for each
- 4 replay scenario families (16 scenarios): credential_change, account_substitution, password_takeover, superadmin_escalation
- Demo scripts: demo_local.py (deterministic), demo_agent.py (LLM-driven via MCP), shared investigation logic
- Milestone 5: Investigation MCP server -- orchestration layer calling identity + case servers via MCP subprocess
- Investigation pivots and evidence aggregation: 5 pivot tools, 4 aggregation categories, pipeline saves default pivots

## Doing

## Blocked

None
