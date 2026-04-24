"""MCP client helpers for the investigation pipeline.

Thin wrappers around mcp.client.stdio for launching and communicating
with identity and case MCP servers as subprocesses.
"""
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


_PROJECT_ROOT = str(Path(__file__).parent.parent.parent.parent)


@asynccontextmanager
async def open_mcp_session(
    command: str,
    args: list[str],
    logger: logging.Logger,
):
    """Launch an MCP server subprocess and yield a ClientSession.

    Guarantees subprocess teardown even on exceptions.
    Sets PYTHONPATH to project root so subprocess imports resolve.
    """
    env = {**os.environ, "PYTHONPATH": _PROJECT_ROOT}

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            logger.info(
                "MCP session opened",
                extra={"command": command, "server_args": args},
            )
            yield session


async def call_tool(
    session: ClientSession,
    tool_name: str,
    arguments: dict,
    logger: logging.Logger,
) -> dict:
    """Call an MCP tool and return the parsed result dict.

    Handles:
    - isError flag on CallToolResult
    - Multiple content parts (collects all text parts)
    - Non-text content parts (skipped)
    - Empty content list (returns empty dict)
    - JSON parse failures (logs warning, returns error dict)
    """
    result = await session.call_tool(tool_name, arguments)

    if result.isError:
        text_parts = []
        for part in result.content:
            if hasattr(part, "text"):
                text_parts.append(part.text)
        error_text = " ".join(text_parts) if text_parts else "Unknown error"
        logger.warning(
            "MCP tool returned error",
            extra={"tool": tool_name, "error": error_text},
        )
        return {"status": "error", "error": {"code": "tool_error", "message": error_text}}

    if not result.content:
        return {}

    # Collect all text parts
    text_parts = []
    for part in result.content:
        if hasattr(part, "text"):
            text_parts.append(part.text)

    if not text_parts:
        return {}

    combined = " ".join(text_parts)

    try:
        return json.loads(combined)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning(
            "Failed to parse MCP tool response as JSON",
            extra={"tool": tool_name, "error": str(exc), "raw": combined[:200]},
        )
        return {"status": "error", "error": {"code": "parse_error", "message": str(exc)}}
