"""Integration tests for the investigation MCP server.

Tests the full MCP transport: launch investigation server via stdio,
call tools, verify responses parse correctly.
"""
import json
import os
import tempfile

import pytest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def _connect(cases_dir: str | None = None):
    """Return an async context manager for an investigation MCP session.

    All tests use an isolated temp cases_dir to prevent shared state.
    """
    if cases_dir is None:
        cases_dir = tempfile.mkdtemp(prefix="blindsight_test_inv_")
    env = {**os.environ, "PYTHONPATH": _PROJECT_ROOT}
    params = StdioServerParameters(
        command="python",
        args=[f"{_PROJECT_ROOT}/src/servers/investigation_mcp.py", cases_dir],
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
                assert "likelihood" in data
                assert "confidence" in data
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


class TestFollowUpTools:
    """Tests for the follow-up case query tools (ADR-0008)."""

    async def test_new_tools_listed(self):
        """Server exposes all 9 tools (2 original + 6 follow-up + 1 report)."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                expected = {
                    "run_investigation_tool",
                    "describe_scenario",
                    "list_cases",
                    "get_case_timeline",
                    "query_case_events",
                    "query_case_entities",
                    "query_case_neighbors",
                    "get_case_tool_call_history",
                    "generate_report",
                }
                assert expected == names, f"Missing tools: {expected - names}"

    async def test_case_not_found_error(self):
        """Follow-up tool with nonexistent case_id returns case_not_found."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_case_timeline",
                    {"case_id": "does_not_exist"},
                )
                data = json.loads(result.content[0].text)
                assert data["status"] == "error"
                assert data["error"]["code"] == "case_not_found"

    async def test_invalid_case_id_error(self):
        """Follow-up tool with path traversal case_id returns invalid_case_id."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_case_timeline",
                    {"case_id": "../etc/passwd"},
                )
                data = json.loads(result.content[0].text)
                assert data["status"] == "error"
                assert data["error"]["code"] == "invalid_case_id"

    async def test_list_cases_empty(self):
        """list_cases on empty cases_dir returns empty list."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("list_cases", {})
                data = json.loads(result.content[0].text)
                assert data["cases"] == []

    async def test_followup_timeline_after_investigation(self):
        """Run investigation, then query timeline via follow-up tool."""
        cases_dir = tempfile.mkdtemp(prefix="blindsight_test_followup_")
        async with await _connect(cases_dir) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Run investigation
                inv_result = await session.call_tool(
                    "run_investigation_tool",
                    {"scenario_name": "credential_change_baseline"},
                )
                assert not inv_result.isError, (
                    f"Investigation failed: {inv_result.content[0].text}"
                )
                inv_data = json.loads(inv_result.content[0].text)
                case_id = inv_data["case_id"]
                assert case_id is not None

                # Query timeline
                tl_result = await session.call_tool(
                    "get_case_timeline",
                    {"case_id": case_id},
                )
                tl_data = json.loads(tl_result.content[0].text)
                assert tl_data["status"] == "success"
                assert tl_data["domain"] == "case"
                assert "events" in tl_data
                assert len(tl_data["events"]) > 0

    async def test_list_cases_after_investigation(self):
        """list_cases returns case metadata after investigation."""
        cases_dir = tempfile.mkdtemp(prefix="blindsight_test_listcases_")
        async with await _connect(cases_dir) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Run investigation
                inv_result = await session.call_tool(
                    "run_investigation_tool",
                    {"scenario_name": "credential_change_baseline"},
                )
                inv_data = json.loads(inv_result.content[0].text)
                case_id = inv_data["case_id"]

                # List cases
                list_result = await session.call_tool("list_cases", {})
                list_data = json.loads(list_result.content[0].text)
                assert len(list_data["cases"]) >= 1
                case_ids = [c["case_id"] for c in list_data["cases"]]
                assert case_id in case_ids

                # Check metadata present
                case_entry = next(c for c in list_data["cases"] if c["case_id"] == case_id)
                assert "title" in case_entry
                assert "status" in case_entry
                assert "severity" in case_entry

    async def test_list_cases_discovers_existing_db(self):
        """list_cases discovers a case DB created outside this server session.

        Creates a case via the case MCP server directly, then launches a
        fresh investigation server against the same directory. Proves
        filesystem-backed discovery works across server restarts.
        """
        cases_dir = tempfile.mkdtemp(prefix="blindsight_test_discover_")

        # Create a case via case server directly
        from src.services.investigation.mcp_client import open_mcp_session, call_tool
        import logging
        logger = logging.getLogger("test_discover")
        logger.setLevel(logging.WARNING)

        async with open_mcp_session(
            "python",
            [f"{_PROJECT_ROOT}/src/servers/case_mcp.py", cases_dir],
            logger,
        ) as case_session:
            create_result = await call_tool(
                case_session, "create_case_tool",
                {"title": "Externally created case"},
                logger,
            )
            assert create_result.get("status") == "success"
            ext_case_id = create_result["results"][0]["id"]

        # Launch investigation server against same dir and list cases
        async with await _connect(cases_dir) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                list_result = await session.call_tool("list_cases", {})
                list_data = json.loads(list_result.content[0].text)
                case_ids = [c["case_id"] for c in list_data["cases"]]
                assert ext_case_id in case_ids, (
                    f"Expected {ext_case_id} in discovered cases, got: {case_ids}"
                )
