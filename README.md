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
pipx install blindsight
blindsight install
```

`blindsight install` writes the investigation MCP server into your Claude Code config (`~/.claude/settings.json` by default; pass `--project` to use `./.mcp.json` instead) and seeds `~/.blindsight/cases/` for case storage. Restart Claude Code to pick up the change.

The bundled replay scenarios are available immediately. Override the scenarios directory with `BLINDSIGHT_SCENARIOS_DIR` and the case store with `BLINDSIGHT_CASES_DIR`. LLM-driven investigations need `ANTHROPIC_API_KEY` in the environment.

CLI usage:

```bash
blindsight describe-scenario                              # list bundled scenarios
blindsight describe-scenario credential_change_baseline   # describe one
blindsight run-investigation credential_change_baseline   # run an investigation
blindsight generate-report <case-id>                      # render a Markdown report
```

## Development setup

```bash
git clone https://github.com/willstull/blindsight
cd blindsight
poetry install
poetry run pytest -q
```

The investigation MCP server is wired up in this repo's `.mcp.json` for local dev — no separate `blindsight install` step needed when working from the source tree.
