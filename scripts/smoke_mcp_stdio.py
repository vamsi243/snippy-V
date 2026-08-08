"""Smoke-test a Snippy MCP stdio executable.

This intentionally calls a geometry-only MCP tool so CI does not need screen
recording permission on macOS or an interactive desktop on Windows.
"""

from __future__ import annotations

import argparse
import asyncio
import json

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def _run(command: str, args: list[str]) -> None:
    transport = StdioTransport(command=command, args=args)
    client = Client(transport, timeout=20, init_timeout=20)

    async with client:
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools}
        required = {"snippy_measure_region", "snippy_get_monitor_layout"}
        missing = required - tool_names
        if missing:
            raise RuntimeError(f"Missing expected MCP tools: {sorted(missing)}")

        result = await client.call_tool(
            "snippy_measure_region",
            {"x1": 1, "y1": 2, "x2": 11, "y2": 22},
        )
        data = result.data
        expected = {"width": 10, "height": 20}
        if not isinstance(data, dict) or data.get("dimensions_px") != expected:
            raise RuntimeError(f"Unexpected snippy_measure_region result: {data!r}")

        print(
            json.dumps(
                {
                    "status": "ok",
                    "tool_count": len(tools),
                    "measure_result": data,
                },
                indent=2,
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test Snippy MCP stdio")
    parser.add_argument("command", help="Executable or script to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for command")
    parsed = parser.parse_args()

    asyncio.run(_run(parsed.command, parsed.args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
