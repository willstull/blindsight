"""Integration tests for the investigation MCP server.

Tests the full MCP transport: launch investigation server via stdio,
call tools, verify responses parse correctly.
"""
import json
import os

import pytest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _connect():
    """Return an async context manager for an investigation MCP session."""
    env = {**os.environ, "PYTHONPATH": _PROJECT_ROOT}
    params = StdioServerParameters(
        command="python",
        args=[f"{_PROJECT_ROOT}/src/servers/investigation_mcp.py"],
        env=env,
    )
    return stdio_client(params)


class TestInvestigationMCP:
    async def test_server_lists_tools(self):
        """Server exposes run_investigation_tool and describe_scenario."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = [t.name for t in tools.tools]
                assert "run_investigation_tool" in names
                assert "describe_scenario" in names

    async def test_describe_scenario_lists_all(self):
        """describe_scenario with no args returns all available scenarios."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("describe_scenario", {})
                data = json.loads(result.content[0].text)
                scenarios = data["scenarios"]
                assert len(scenarios) > 0
                names = [s["name"] for s in scenarios]
                assert "credential_change_baseline" in names

    async def test_describe_scenario_single(self):
        """describe_scenario with a name returns that scenario's details."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "describe_scenario",
                    {"scenario_name": "credential_change_baseline"},
                )
                data = json.loads(result.content[0].text)
                assert data["scenario_name"] == "credential_change_baseline"
                assert "investigation_question" in data
                assert "time_range" in data

    async def test_describe_scenario_not_found(self):
        """describe_scenario with unknown name returns error + available list."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "describe_scenario",
                    {"scenario_name": "nonexistent_scenario"},
                )
                data = json.loads(result.content[0].text)
                assert data["status"] == "error"
                assert "available" in data

    async def test_run_investigation_produces_report(self):
        """run_investigation_tool returns a valid InvestigationReport shape."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "run_investigation_tool",
                    {"scenario_name": "credential_change_baseline"},
                )
                assert not result.isError, (
                    f"Tool returned error: {result.content[0].text if result.content else 'unknown'}"
                )
                data = json.loads(result.content[0].text)

                # Verify required fields
                assert data["scenario_name"] == "credential_change_baseline"
                assert "investigation_question" in data
                assert "hypothesis" in data
                assert "likelihood_score" in data
                assert "confidence_limit" in data
                assert "steps" in data
                assert "case_id" in data
                assert data["case_id"] is not None
                assert data["tool_calls_used"] > 0
                assert data["total_events_evaluated"] > 0

    async def test_run_investigation_not_found(self):
        """run_investigation_tool with unknown scenario returns error."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "run_investigation_tool",
                    {"scenario_name": "nonexistent_scenario"},
                )
                data = json.loads(result.content[0].text)
                assert data["status"] == "error"
                assert data["error"]["code"] == "scenario_not_found"
