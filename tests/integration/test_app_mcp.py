"""Integration tests for the app domain MCP server.

Connects to the server via stdio subprocess and verifies tool responses.
"""
import json
import logging
import sys

import pytest

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from tests.conftest import FIXTURES_DIR


_SCENARIO = str(FIXTURES_DIR / "account_substitution_baseline")


async def _connect():
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "blindsight.servers.app_mcp", _SCENARIO],
    )
    return stdio_client(server_params)


class TestAppMCPTools:
    async def test_tool_listing(self):
        """App server should list 7 core tools."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                assert "describe_domain" in tool_names
                assert "describe_types" in tool_names
                assert "get_entity" in tool_names
                assert "search_entities" in tool_names
                assert "search_events" in tool_names
                assert "get_neighbors" in tool_names
                assert "describe_coverage" in tool_names
                assert len(tool_names) == 7

    async def test_search_events_returns_app_events(self):
        """search_events should return app domain events."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("search_events", {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                })
                data = json.loads(result.content[0].text)
                assert data["domain"] == "app"
                assert len(data["events"]) > 0
                assert all(e["domain"] == "app" for e in data["events"])

    async def test_describe_coverage_complete(self):
        """describe_coverage should return complete status."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("describe_coverage", {
                    "time_range_start": "2026-03-01T00:00:00Z",
                    "time_range_end": "2026-03-31T23:59:59Z",
                })
                data = json.loads(result.content[0].text)
                assert data["coverage_report"]["overall_status"] == "complete"
                assert data["domain"] == "app"

    async def test_get_entity_resource(self):
        """get_entity should return a resource entity."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("get_entity", {
                    "entity_id": "resource_financial_system",
                })
                data = json.loads(result.content[0].text)
                assert len(data["entities"]) == 1
                assert data["entities"][0]["kind"] == "application"

    async def test_describe_domain_returns_app(self):
        """describe_domain should identify as app domain."""
        async with await _connect() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("describe_domain", {})
                data = json.loads(result.content[0].text)
                assert data["domain"] == "app"
                assert "app." in data["capabilities"]["supported_actions_prefixes"]
