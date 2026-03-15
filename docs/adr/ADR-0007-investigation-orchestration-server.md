# ADR-0007: Investigation Orchestration Server

## Status

Accepted

## Context

Blindsight has domain servers (identity) and a case server, but no orchestration layer. Clients must know the correct sequence of identity + case tool calls to run an investigation. The demo scripts (`demo_local.py`, `demo_agent.py`) each implement their own investigation loops, duplicating logic around evidence search, scoring, and case management.

ADR-0006 defines shared tool contracts for evidence domains. The investigation server is a different kind of server -- an orchestrator, not a domain. It does not implement the domain tool contract (`describe_domain`, `search_entities`, etc.) but instead composes domain and case servers to run bounded investigations.

## Decision

Add a third MCP server (`src/servers/investigation_mcp.py`) that orchestrates identity and case servers via MCP stdio subprocess.

**Key design choices:**

1. **MCP subprocess boundary**: The investigation server calls identity and case servers via `mcp.client.stdio`, not via direct function import. This proves the tool boundary end-to-end and keeps the investigation server decoupled from domain internals.

2. **Per-investigation subprocess lifecycle**: Each `run_investigation` call spins up fresh identity + case server subprocesses, runs the pipeline, and tears them down. No cross-contamination between investigation runs.

3. **Two modes -- mechanical and LLM**: Mechanical mode is deterministic (no LLM, reproducible results). LLM mode uses the same mechanical scores but generates natural language narrative. Mechanical scores (likelihood_score, confidence_limit) are always from the scoring functions, never from the LLM.

4. **Own tool surface**: The investigation server exposes `run_investigation` and `describe_scenario`, not the domain tool contract. It is an orchestrator, not an evidence source.

5. **Scoring extracted to reusable functions**: `src/services/investigation/scoring.py` contains pure functions for building evidence items, claims, hypotheses, and narrative text. These are imported by both the pipeline and the demo scripts.

6. **Manifest is authoritative**: The scenario manifest provides default investigation question and time range. Tool parameters are optional overrides.

## Rationale

- Centralizing the investigation loop in a server rather than scripts makes the investigation reproducible and accessible to any MCP client.
- The subprocess boundary enforces the same contract discipline clients face -- the investigation server cannot reach into domain internals.
- Per-investigation lifecycle prevents state leakage that could affect reproducibility.
- Separating mechanical from LLM narrative keeps the scoring deterministic and testable while allowing human-readable output when needed.

## Consequences

- Three MCP servers instead of two. The investigation server depends on the other two being launchable as subprocesses.
- Each investigation run incurs subprocess startup overhead. Acceptable for investigation workloads (not high-frequency).
- Scoring logic is now shared between the pipeline and demo scripts, reducing duplication but creating a dependency from scripts to `src/services/investigation/`.
- The pipeline has a fixed investigation loop (not agent-driven). `demo_agent.py` remains for free-form LLM exploration.
