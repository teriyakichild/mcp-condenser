"""
mcp_proxy.py — MCP proxy that condenses JSON tool responses via json_condenser.

Sits between an agent and an upstream MCP server, intercepting tool responses
and compressing verbose JSON (e.g. Kubernetes API output) into compact TOON text.

Configuration (environment variables):
    UPSTREAM_MCP_URL  — URL of the upstream MCP server (required)
    CONDENSE_TOOLS    — comma-separated tool names, or * for all (default: *)
    PROXY_HOST        — bind host (default: 0.0.0.0)
    PROXY_PORT        — bind port (default: 9000)

Usage:
    UPSTREAM_MCP_URL=http://localhost:8080/mcp python mcp_proxy.py
"""

import json
import os
import sys

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from json_condenser import condense_json, stats


class CondenserMiddleware(Middleware):
    """Intercepts tool call responses and condenses JSON into TOON text."""

    def __init__(self, tools_allowlist: set[str] | None = None):
        """
        Args:
            tools_allowlist: Set of tool names to condense, or None for all tools.
        """
        super().__init__()
        self.tools_allowlist = tools_allowlist

    async def on_call_tool(self, context, call_next) -> ToolResult:
        tool_name = context.message.name
        result = await call_next(context)

        if self.tools_allowlist is not None and tool_name not in self.tools_allowlist:
            return result

        for item in result.content:
            if not isinstance(item, TextContent):
                continue
            try:
                data = json.loads(item.text)
            except (json.JSONDecodeError, TypeError):
                continue

            orig_text = item.text
            condensed = condense_json(data)
            item.text = condensed

            s = stats(orig_text, condensed)
            print(
                f"[condenser] {tool_name}: "
                f"{s['orig_tok']:,}→{s['cond_tok']:,} tokens "
                f"({s['tok_pct']}% reduction)",
                file=sys.stderr,
            )

        return result


def main():
    upstream_url = os.environ.get("UPSTREAM_MCP_URL")
    if not upstream_url:
        print("error: UPSTREAM_MCP_URL environment variable is required", file=sys.stderr)
        sys.exit(1)

    condense_tools_env = os.environ.get("CONDENSE_TOOLS", "*").strip()
    if condense_tools_env == "*":
        tools_allowlist = None
    else:
        tools_allowlist = {t.strip() for t in condense_tools_env.split(",") if t.strip()}

    host = os.environ.get("PROXY_HOST", "0.0.0.0")
    port = int(os.environ.get("PROXY_PORT", "9000"))

    proxy = FastMCP.as_proxy(upstream_url)
    proxy.add_middleware(CondenserMiddleware(tools_allowlist))

    print(f"MCP condenser proxy starting on {host}:{port}", file=sys.stderr)
    print(f"  upstream: {upstream_url}", file=sys.stderr)
    print(
        f"  condensing: {condense_tools_env}",
        file=sys.stderr,
    )

    proxy.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
