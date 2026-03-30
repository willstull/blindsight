"""Integration tests for investigation pivot MCP tools.

Starts the case MCP server as a subprocess and exercises all 5 pivot
tools via MCP protocol. Tests are deterministic.
"""
import json
import logging
import os

import pytest

from src.services.investigation.mcp_client import open_mcp_session, call_tool

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _logger():
    logger = logging.getLogger("test_case_pivot_mcp")
    logger.setLevel(logging.WARNING)
    return logger


async def _setup_case(cases_dir: str, logger):
    """Start case server, create a case, ingest some events, return (session_ctx, case_id)."""
    session_ctx = open_mcp_session(
        "python",
        [f"{_PROJECT_ROOT}/src/servers/case_mcp.py", cases_dir],
        logger,
    )
    return session_ctx


class TestPivotMCPTools:
    async def test_save_list_get_roundtrip(self, tmp_path):
        logger = _logger()
        cases_dir = str(tmp_path / "cases")
        os.makedirs(cases_dir, exist_ok=True)

        async with open_mcp_session(
            "python",
            [f"{_PROJECT_ROOT}/src/servers/case_mcp.py", cases_dir],
            logger,
        ) as session:
            # Create a case
            case_result = await call_tool(session, "create_case_tool", {
                "title": "Pivot test case",
            }, logger)
            case_id = case_result["results"][0]["id"]

            # Ingest some events
            await call_tool(session, "ingest_records", {
                "case_id": case_id,
                "domain_response": {
                    "events": [
                        {
                            "id": "evt-1", "tlp": "GREEN", "domain": "identity",
                            "ts": "2026-01-10T10:00:00Z", "action": "auth.login",
                            "actor": {"actor_entity_id": "principal_alice"},
                            "targets": [], "outcome": "succeeded", "raw_refs": [],
                        },
                        {
                            "id": "evt-2", "tlp": "GREEN", "domain": "identity",
                            "ts": "2026-01-10T10:05:00Z", "action": "credential.reset",
                            "actor": {"actor_entity_id": "principal_alice"},
                            "targets": [{"target_entity_id": "cred_pw", "role": "subject"}],
                            "outcome": "succeeded", "raw_refs": [],
                        },
                        {
                            "id": "evt-3", "tlp": "GREEN", "domain": "identity",
                            "ts": "2026-01-10T10:06:00Z", "action": "credential.enroll",
                            "actor": {"actor_entity_id": "principal_alice"},
                            "targets": [{"target_entity_id": "cred_mfa", "role": "subject"}],
                            "outcome": "succeeded", "raw_refs": [],
                        },
                    ],
                },
            }, logger)

            # Save a pivot
            save_result = await call_tool(session, "save_investigation_pivot_tool", {
                "case_id": case_id,
                "label": "evidence_slice",
                "event_ids": ["evt-1", "evt-2", "evt-3"],
                "entity_ids": ["principal_alice"],
                "relationship_ids": [],
                "description": "Test pivot",
                "focal_entity_ids": ["principal_alice"],
            }, logger)
            assert save_result["status"] == "success"
            pivot = save_result["results"][0]
            pivot_id = pivot["id"]
            assert pivot["label"] == "evidence_slice"

            # List pivots
            list_result = await call_tool(session, "list_investigation_pivots_tool", {
                "case_id": case_id,
            }, logger)
            assert list_result["status"] == "success"
            assert len(list_result["results"]) == 1
            assert list_result["results"][0]["id"] == pivot_id

            # Get pivot
            get_result = await call_tool(session, "get_investigation_pivot_tool", {
                "case_id": case_id,
                "pivot_id": pivot_id,
            }, logger)
            assert get_result["status"] == "success"
            assert get_result["results"][0]["label"] == "evidence_slice"

    async def test_query_pivot_timeline_returns_ordered_events(self, tmp_path):
        logger = _logger()
        cases_dir = str(tmp_path / "cases")
        os.makedirs(cases_dir, exist_ok=True)

        async with open_mcp_session(
            "python",
            [f"{_PROJECT_ROOT}/src/servers/case_mcp.py", cases_dir],
            logger,
        ) as session:
            case_result = await call_tool(session, "create_case_tool", {
                "title": "Timeline test",
            }, logger)
            case_id = case_result["results"][0]["id"]

            await call_tool(session, "ingest_records", {
                "case_id": case_id,
                "domain_response": {
                    "events": [
                        {
                            "id": "evt-b", "tlp": "GREEN", "domain": "identity",
                            "ts": "2026-01-15T14:00:00Z", "action": "auth.login",
                            "actor": {"actor_entity_id": "principal_bob"},
                            "targets": [], "outcome": "succeeded", "raw_refs": [],
                        },
                        {
                            "id": "evt-a", "tlp": "GREEN", "domain": "identity",
                            "ts": "2026-01-10T10:00:00Z", "action": "auth.login",
                            "actor": {"actor_entity_id": "principal_alice"},
                            "targets": [], "outcome": "succeeded", "raw_refs": [],
                        },
                    ],
                },
            }, logger)

            save_result = await call_tool(session, "save_investigation_pivot_tool", {
                "case_id": case_id,
                "label": "timeline_test",
                "event_ids": ["evt-a", "evt-b"],
                "entity_ids": [],
                "relationship_ids": ["r1"],
            }, logger)
            pivot_id = save_result["results"][0]["id"]

            timeline = await call_tool(session, "query_pivot_timeline_tool", {
                "case_id": case_id,
                "pivot_id": pivot_id,
            }, logger)
            assert timeline["status"] == "success"
            events = timeline["events"]
            assert len(events) == 2
            assert events[0]["id"] == "evt-a"
            assert events[1]["id"] == "evt-b"

    async def test_find_event_clusters_returns_clusters(self, tmp_path):
        logger = _logger()
        cases_dir = str(tmp_path / "cases")
        os.makedirs(cases_dir, exist_ok=True)

        async with open_mcp_session(
            "python",
            [f"{_PROJECT_ROOT}/src/servers/case_mcp.py", cases_dir],
            logger,
        ) as session:
            case_result = await call_tool(session, "create_case_tool", {
                "title": "Cluster test",
            }, logger)
            case_id = case_result["results"][0]["id"]

            events = []
            for i in range(5):
                events.append({
                    "id": f"cl-{i}", "tlp": "GREEN", "domain": "identity",
                    "ts": f"2026-01-10T10:{i:02d}:00Z", "action": "auth.login",
                    "actor": {"actor_entity_id": "principal_alice"},
                    "targets": [], "outcome": "succeeded", "raw_refs": [],
                })
            await call_tool(session, "ingest_records", {
                "case_id": case_id,
                "domain_response": {"events": events},
            }, logger)

            save_result = await call_tool(session, "save_investigation_pivot_tool", {
                "case_id": case_id,
                "label": "cluster_test",
                "event_ids": [f"cl-{i}" for i in range(5)],
                "entity_ids": [],
                "relationship_ids": ["r1"],
            }, logger)
            pivot_id = save_result["results"][0]["id"]

            clusters = await call_tool(session, "find_event_clusters_tool", {
                "case_id": case_id,
                "pivot_id": pivot_id,
            }, logger)
            assert clusters["status"] == "success"
            assert len(clusters["results"]) == 1
            assert clusters["results"][0]["event_count"] == 5

    async def test_invalid_case_id_returns_error(self, tmp_path):
        logger = _logger()
        cases_dir = str(tmp_path / "cases")
        os.makedirs(cases_dir, exist_ok=True)

        async with open_mcp_session(
            "python",
            [f"{_PROJECT_ROOT}/src/servers/case_mcp.py", cases_dir],
            logger,
        ) as session:
            result = await call_tool(session, "save_investigation_pivot_tool", {
                "case_id": "../../bad",
                "label": "test",
                "event_ids": ["e1"],
                "entity_ids": [],
                "relationship_ids": [],
            }, logger)
            assert result["status"] == "error"
            assert result["error"]["code"] == "invalid_case_id"

    async def test_nonexistent_pivot_returns_error(self, tmp_path):
        logger = _logger()
        cases_dir = str(tmp_path / "cases")
        os.makedirs(cases_dir, exist_ok=True)

        async with open_mcp_session(
            "python",
            [f"{_PROJECT_ROOT}/src/servers/case_mcp.py", cases_dir],
            logger,
        ) as session:
            case_result = await call_tool(session, "create_case_tool", {
                "title": "Error test",
            }, logger)
            case_id = case_result["results"][0]["id"]

            result = await call_tool(session, "get_investigation_pivot_tool", {
                "case_id": case_id,
                "pivot_id": "nonexistent-pivot-id",
            }, logger)
            assert result["status"] == "error"
            assert result["error"]["code"] == "pivot_not_found"
