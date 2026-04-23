# Blindsight

Coverage-aware incident investigation through MCP.

Blindsight helps incident responders answer scope, containment, and impact questions by querying existing telemetry systems in place. It normalizes evidence from multiple domains into a common model, tracks what can and cannot be verified through explicit coverage reports, and produces reproducible case records with analyst-ready reports.

## How it works

Blindsight runs bounded investigations across evidence domains (identity, application) through MCP tool interfaces. Each investigation:

1. Queries domain servers for entities, events, relationships, and coverage
2. Correlates evidence across domains in a persistent case store
3. Scores likelihood and confidence separately -- likelihood reflects the evidence pattern, confidence reflects what the available data can verify
4. Classifies coverage gaps by relevance to the specific hypothesis
5. Generates a structured incident report from the saved case

The system is read-only against upstream telemetry. It queries systems already in place rather than building a new log platform.

## Architecture

Four MCP servers:

| Server | Role |
|--------|------|
| Identity MCP | Evidence domain: account lifecycle, credentials, privilege events |
| App MCP | Evidence domain: user activity, transactions, application events |
| Investigation MCP | Orchestration: runs investigations, generates reports, follow-up queries |
| Case MCP | Persistence: DuckDB-backed case store with correlation queries |

Evidence domains are replay-backed, reading from NDJSON fixture files. The same domain contract supports live integrations without changing the investigation pipeline.

## Evaluation

Testing uses replay scenarios with known outcomes. Each scenario family includes a baseline and degraded variants (retention gaps, missing fields, missing sources) that verify the system correctly reduces confidence when evidence is incomplete.

## Documentation

See [docs/index.md](docs/index.md) for specifications, architecture decisions, and implementation details.

## Quick start

```bash
# Install dependencies
poetry install

# Run tests
poetry run pytest -q

# Run an investigation via MCP (requires .env with ANTHROPIC_API_KEY for LLM features)
# The investigation MCP server is configured in .mcp.json
```

