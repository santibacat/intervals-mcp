"""Perform a real MCP stdio handshake and list the exposed tools."""

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {
    "get_personal_context",
    "set_personal_fact",
    "get_training_context",
    "list_draft_plans",
    "get_draft_plan",
    "create_draft_plan",
    "clone_draft_plan",
    "rename_draft_plan",
    "add_workout_to_draft",
    "update_draft_workout",
    "schedule_draft_plan",
    "unschedule_draft_plan",
}


async def smoke_test() -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "intervals_mcp.mcp_server"],
    )
    async with (
        stdio_client(server) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        response = await session.list_tools()

    names = {tool.name for tool in response.tools}
    if names != EXPECTED_TOOLS:
        raise RuntimeError(f"Unexpected MCP tools: {sorted(names)}")
    if any("event" in name for name in names):
        raise RuntimeError("Generic calendar mutation tool detected")
    print(f"MCP stdio handshake OK; {len(names)} safe tools exposed")


if __name__ == "__main__":
    asyncio.run(smoke_test())
