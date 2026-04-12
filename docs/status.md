# Current Status

## Done

- Core ontology, identity contract, MCP patterns, normalized output spec, replay dataset contract, integration interface, ADRs 1-6
- Milestone 1: Replay-backed identity MCP server (10 tools, factory pattern, replay integration)
- Milestone 4: DuckDB case store (9 tools, 11 tables, ingest with upsert, correlation queries)
- Analytic types: EvidenceItem, Claim, Hypothesis, Assumption in core types; ingest functions for each
- 4 replay scenario families (16 scenarios): credential_change, account_substitution, password_takeover, superadmin_escalation
- Demo scripts: demo_local.py (deterministic), demo_agent.py (LLM-driven via MCP), shared investigation logic
- Milestone 5: Investigation MCP server -- orchestration layer calling identity + case servers via MCP subprocess
- Evidence aggregation: 4 aggregation categories (lifecycle_chain, shared_indicator, credential_sequence, action_burst) feeding into claim building and scoring
- Follow-up query tools: 6 tools proxying to case server via MCP subprocess, filesystem-backed discovery (ADR-0008)
- Categorical scoring: likelihood and confidence as low/medium/high bands, LLM-based coverage gap relevance classification, structured GapAssessment output (ADR-0009, supersedes ADR-0005)
- Application domain MCP server: second evidence domain, same 7-tool contract, shared replay base class, multi-domain pipeline with coverage merging and entity merge on ingest (ADR-0010)

## Doing

## Blocked

None
