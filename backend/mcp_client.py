"""Thin MCP client for non-agent callers (the FastAPI routes and the payment CLI).

It launches the same campus-customs MCP server the agents use (stdio) and
calls its tools. It contains no SQL and no business rules: every shop fact and
every payment goes through an MCP tool.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

from config import HW5_ROOT, MCP_PYTHON, MCP_SERVER_PATH


class MCPToolError(Exception):
    """An MCP tool refused or failed (e.g. missing ticket, not enough cash)."""

    def __init__(self, tool: str, message: str):
        super().__init__(message)
        self.tool = tool
        self.message = message


def new_client() -> Client:
    return Client(StdioTransport(command=MCP_PYTHON, args=[str(MCP_SERVER_PATH)], cwd=str(HW5_ROOT)))


def _clean(message: str) -> str:
    # fastmcp prefixes server errors with "Error calling tool '<name>': ".
    return message.split("': ", 1)[1] if message.startswith("Error calling tool '") else message


async def call_tool(client: Client, name: str, args: dict[str, Any] | None = None) -> dict:
    try:
        result = await client.call_tool(name, args or {})
    except Exception as exc:
        raise MCPToolError(name, _clean(str(exc))) from exc
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


class ShopMCP:
    """One long-lived MCP connection shared by all API requests."""

    def __init__(self) -> None:
        self._client = new_client()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        await self._client.__aenter__()

    async def stop(self) -> None:
        await self._client.__aexit__(None, None, None)

    async def call(self, name: str, args: dict[str, Any] | None = None) -> dict:
        async with self._lock:  # one request at a time on the shared stdio session
            return await call_tool(self._client, name, args)
