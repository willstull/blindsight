#!/usr/bin/env python3
"""Demo: LLM-driven incident investigation via MCP.

An LLM agent autonomously investigates incidents by calling Blindsight's
MCP tools. This is the first demo that goes through the actual MCP
interface rather than calling integration functions directly.

The agent:
  1. Receives an investigation question from the scenario manifest
  2. Decides which tools to call (coverage, entities, events, etc.)
  3. Interprets results in natural language at each step
  4. Produces a structured hypothesis with likelihood, confidence, and gaps

Architecture:
  pydantic-ai Agent <--stdio--> identity_mcp.py (scenario data)
  pydantic-ai Agent <--stdio--> case_mcp.py     (case store)

Usage:
    ANTHROPIC_API_KEY=... poetry run python scripts/demo_agent.py

Environment variables:
    BLINDSIGHT_MODEL          Model to use (default: anthropic:claude-sonnet-4-20250514)
    BLINDSIGHT_MAX_TOOL_CALLS Max tool calls per run (default: 30)
"""
import asyncio
import json
import logging
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio
from pydantic_ai.usage import UsageLimits

from scripts._investigation import (
    heading, step, narrate, load_manifest,
    discover_scenarios, select_scenarios,
    DIVIDER, SECTION,
)


# -- Structured output types --

class InvestigationStep(BaseModel):
    stage: str
    description: str
    tool_calls: list[str]
    key_findings: list[str]


class InvestigationReport(BaseModel):
    scenario_name: str
    investigation_question: str
    steps: list[InvestigationStep]
    hypothesis: str
    likelihood_assessment: str
    confidence_assessment: str
    likelihood_score: float
    confidence_limit: float
    gaps: list[str]
    next_steps: list[str]


# -- System prompt --

SYSTEM_PROMPT = """\
You are a security incident investigator using the Blindsight system.
You have access to two sets of MCP tools:

1. **Identity domain tools** (blindsight-identity): Query identity telemetry
   - describe_domain: Get domain capabilities and supported action types
   - describe_types: Get entity/relationship type schemas
   - describe_coverage: Check data availability and gaps for a time range
   - search_entities: Find entities (principals, credentials, sessions, etc.)
   - search_events: Find normalized events within a time range
   - get_entity: Fetch a single entity by ID
   - get_neighbors: Traverse relationships from an entity
   - get_principal: Fetch a principal by ID
   - resolve_principal: Find principals by identifiers
   - list_credential_changes: List credential changes for a principal

2. **Case store tools** (blindsight-case): Manage investigation cases
   - create_case_tool: Create a new investigation case
   - ingest_records: Ingest a domain tool response into the case
   - get_timeline_tool: Get chronological event timeline
   - query_entities_tool: Query entities in a case
   - query_events_tool: Query events in a case
   - query_neighbors_tool: Find connected entities in a case
   - get_tool_call_history_tool: Get tool call audit trail

## Investigation methodology

Follow this structured approach:

1. **Create a case**: Use create_case_tool to open an investigation case. Note the case_id from the response.

2. **Check coverage**: Use describe_coverage with the investigation time range. Report what data sources are available and what gaps exist. This determines your confidence ceiling.

3. **Discover entities**: Use search_entities to find principals and other relevant entities. Do not hardcode entity IDs.

4. **Map relationships**: Use get_neighbors to understand what credentials, sessions, and devices are linked to the subject.

5. **Discover action types**: Use describe_domain to learn what action types are available.

6. **Search for evidence**: Use search_events with relevant action filters. Look for credential changes, privilege changes, account lifecycle events -- not just logins.

7. **Ingest into case**: Use ingest_records to store at least one identity domain response in the case store. Pass the case_id and the full domain response dict.

8. **Build timeline**: Use get_timeline_tool with the case_id to see the chronological sequence of events from ingested data.

9. **Assess**: Synthesize findings into a hypothesis.

## REQUIRED tool usage

You MUST use all of these tools during the investigation:
- create_case_tool (create the case)
- describe_coverage (check data availability)
- search_events (find evidence)
- ingest_records (store domain response in case)
- get_timeline_tool (query case timeline)

## Key principles

- **Coverage-aware reasoning**: Separate what evidence suggests (likelihood) from what you can verify (confidence limit). If coverage is partial, your confidence limit must reflect that.
- **Absence vs. evidence**: Not finding something in partial coverage is NOT the same as confirming it didn't happen.
- **Be explicit about gaps**: State clearly what you cannot determine and why.
- **Natural language interpretation**: At each step, explain what you found and what it means in the context of the investigation question.

## Output

Produce a structured InvestigationReport with:
- Steps taken with natural language descriptions and key findings
- A hypothesis statement
- Likelihood assessment (what evidence suggests)
- Confidence assessment (what we can/can't verify)
- Numerical scores (likelihood_score 0-1, confidence_limit 0-1)
- Identified gaps
- Recommended next steps
"""


def _get_model() -> str:
    return os.environ.get("BLINDSIGHT_MODEL", "anthropic:claude-sonnet-4-20250514")


def _get_max_tool_calls() -> int:
    return int(os.environ.get("BLINDSIGHT_MAX_TOOL_CALLS", "30"))


async def run_agent_investigation(scenario_path: Path) -> InvestigationReport:
    """Run an LLM-driven investigation against a single scenario."""
    manifest = load_manifest(scenario_path)
    time_range = manifest["time_range"]

    heading(f"AGENT INVESTIGATION: {manifest['description']}")
    narrate(f"Question: {manifest['question']}")
    narrate(f"Scenario: {manifest['scenario_name']} (variant={manifest['variant']})")
    narrate(f"Time range: {time_range.start} to {time_range.end}")
    narrate(f"Model: {_get_model()}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="blindsight_agent_"))
    project_root = str(Path(__file__).parent.parent)

    # MCP servers need PYTHONPATH set so `from src...` imports resolve
    server_env = {**os.environ, "PYTHONPATH": project_root}

    identity_server = MCPServerStdio(
        "python",
        args=[str(Path(project_root) / "src" / "servers" / "identity_mcp.py"),
              str(scenario_path)],
        env=server_env,
        cwd=project_root,
    )
    case_server = MCPServerStdio(
        "python",
        args=[str(Path(project_root) / "src" / "servers" / "case_mcp.py"),
              str(tmp_dir)],
        env=server_env,
        cwd=project_root,
    )

    agent = Agent(
        model=_get_model(),
        output_type=InvestigationReport,
        system_prompt=SYSTEM_PROMPT,
        mcp_servers=[identity_server, case_server],
    )

    user_message = (
        f"Investigate the following question:\n\n"
        f"**Question**: {manifest['question']}\n\n"
        f"**Time range**: {time_range.start} to {time_range.end}\n\n"
        f"**Scenario**: {manifest['scenario_name']}\n\n"
        f"Use the identity domain tools to gather evidence and the case store "
        f"tools to track your investigation. Follow the methodology described "
        f"in your instructions."
    )

    max_calls = _get_max_tool_calls()
    step(f"Running agent (model={_get_model()}, tool_budget={max_calls})")

    async with identity_server, case_server:
        result = await agent.run(
            user_message,
            usage_limits=UsageLimits(request_limit=max_calls),
        )

    report = result.output

    # Print the report
    _print_report(report)
    _print_usage(result.usage())

    return report


def _print_report(report: InvestigationReport) -> None:
    """Print the structured investigation report."""
    step("Investigation steps")
    for i, s in enumerate(report.steps, 1):
        print(f"\n  Step {i}: {s.stage}")
        print(f"  {'-' * 40}")
        for line in s.description.splitlines():
            print(f"    {line}")
        if s.tool_calls:
            print(f"    Tools: {', '.join(s.tool_calls)}")
        if s.key_findings:
            print(f"    Findings:")
            for f in s.key_findings:
                print(f"      - {f}")

    step("Hypothesis")
    for line in report.hypothesis.splitlines():
        narrate(line)

    step("Assessment")
    print(f"  Likelihood ({report.likelihood_score:.2f}):")
    for line in report.likelihood_assessment.splitlines():
        print(f"    {line}")
    print(f"\n  Confidence limit ({report.confidence_limit:.2f}):")
    for line in report.confidence_assessment.splitlines():
        print(f"    {line}")

    if report.gaps:
        step("Gaps")
        for gap in report.gaps:
            print(f"    - {gap}")

    if report.next_steps:
        step("Recommended next steps")
        for ns in report.next_steps:
            print(f"    - {ns}")


def _print_usage(usage) -> None:
    """Print token usage summary."""
    print(f"\n  Token usage:")
    print(f"    Requests:        {usage.requests}")
    print(f"    Input tokens:    {usage.request_tokens}")
    print(f"    Output tokens:   {usage.response_tokens}")
    print(f"    Total tokens:    {usage.total_tokens}")


async def main():
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Check for API key
    model = _get_model()
    if model.startswith("anthropic:") and not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable is required for Anthropic models.")
        print("Set it with: export ANTHROPIC_API_KEY=your-key-here")
        print(f"Or use a different model: export BLINDSIGHT_MODEL=openai:gpt-4o")
        sys.exit(1)
    elif model.startswith("openai:") and not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable is required for OpenAI models.")
        sys.exit(1)

    families = discover_scenarios()

    heading("BLINDSIGHT AGENT INVESTIGATION DEMO")
    narrate("This demo uses an LLM agent to autonomously investigate incidents")
    narrate("by calling Blindsight's MCP tools. The agent decides which tools")
    narrate("to call, interprets results, and produces a structured hypothesis.")
    narrate(f"Model: {model}")

    scenarios_to_run = await select_scenarios(families)
    if not scenarios_to_run:
        print("  No scenarios selected. Exiting.")
        return

    narrate(f"Running {len(scenarios_to_run)} scenario(s)")

    reports: list[InvestigationReport] = []
    for scenario_path in scenarios_to_run:
        report = await run_agent_investigation(scenario_path)
        reports.append(report)

    # -- Summary --
    if len(reports) > 1:
        heading("COMPARISON SUMMARY")
        for r in reports:
            print(f"  {r.scenario_name}:")
            print(f"    Likelihood:       {r.likelihood_score:.2f}")
            print(f"    Confidence limit: {r.confidence_limit:.2f}")
            print(f"    Gaps:             {len(r.gaps)}")
            print(f"    Steps taken:      {len(r.steps)}")
            print()

    heading("AGENT DEMO COMPLETE")
    narrate(
        "Key takeaway: The LLM agent drives the investigation autonomously,\n"
        "choosing which tools to call and interpreting results in natural\n"
        "language. The MCP interface is the contract boundary -- the agent\n"
        "never accesses integration internals directly."
    )


if __name__ == "__main__":
    asyncio.run(main())
