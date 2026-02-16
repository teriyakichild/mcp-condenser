"""
mcp_proxy.py — MCP proxy that condenses JSON tool responses via json_condenser.

Sits between an agent and an upstream MCP server, intercepting tool responses
and compressing verbose JSON (e.g. Kubernetes API output) into compact TOON text.

Configuration (environment variables):
    UPSTREAM_MCP_URL  — URL of the upstream MCP server (required)
    CONDENSE_TOOLS    — comma-separated tool names, or * for all (default: *)
    TOON_ONLY_TOOLS   — comma-separated tool names for direct JSON→TOON
                         encoding without semantic preprocessing (default: empty)
    TOON_FALLBACK     — when true, JSON results from tools not in either list
                         are still converted to TOON (default: true)
    PROXY_HOST        — bind host (default: 0.0.0.0)
    PROXY_PORT        — bind port (default: 9000)

Processing order for each JSON tool result:
    1. Tool in TOON_ONLY_TOOLS → toon_format.encode (no preprocessing)
    2. Tool in CONDENSE_TOOLS (or *) → condense_json (full pipeline)
    3. JSON detected and TOON_FALLBACK is true → toon_format.encode
    4. Otherwise → pass through unchanged

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

from json_condenser import condense_json, toon_encode_json, stats


class CondenserMiddleware(Middleware):
    """Intercepts tool call responses and condenses JSON into TOON text."""

    def __init__(
        self,
        tools_allowlist: set[str] | None = None,
        toon_only_allowlist: set[str] | None = None,
        toon_fallback: bool = True,
    ):
        """
        Args:
            tools_allowlist: Set of tool names for full condensing, or None for all.
            toon_only_allowlist: Set of tool names for direct TOON encoding (no preprocessing).
            toon_fallback: When True, JSON from unmatched tools is still TOON-encoded.
        """
        super().__init__()
        self.tools_allowlist = tools_allowlist
        self.toon_only_allowlist = toon_only_allowlist or set()
        self.toon_fallback = toon_fallback

    async def on_call_tool(self, context, call_next) -> ToolResult:
        tool_name = context.message.name
        result = await call_next(context)

        for item in result.content:
            if not isinstance(item, TextContent):
                continue
            try:
                data = json.loads(item.text)
            except (json.JSONDecodeError, TypeError):
                continue

            orig_text = item.text

            # 1. TOON_ONLY_TOOLS → direct TOON encoding
            if tool_name in self.toon_only_allowlist:
                condensed = toon_encode_json(data)
                mode = "toon-only"
            # 2. CONDENSE_TOOLS (or *) → full pipeline
            elif self.tools_allowlist is None or tool_name in self.tools_allowlist:
                condensed = condense_json(data)
                mode = "condense"
            # 3. TOON_FALLBACK → direct TOON encoding
            elif self.toon_fallback:
                condensed = toon_encode_json(data)
                mode = "toon-fallback"
            # 4. No match → pass through
            else:
                continue

            item.text = condensed

            s = stats(orig_text, condensed)
            print(
                f"[condenser] {tool_name} ({mode}): "
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

    toon_only_env = os.environ.get("TOON_ONLY_TOOLS", "").strip()
    toon_only_allowlist = {t.strip() for t in toon_only_env.split(",") if t.strip()} if toon_only_env else set()

    toon_fallback_env = os.environ.get("TOON_FALLBACK", "true").strip().lower()
    toon_fallback = toon_fallback_env not in ("false", "0", "no")

    host = os.environ.get("PROXY_HOST", "0.0.0.0")
    port = int(os.environ.get("PROXY_PORT", "9000"))

    proxy = FastMCP.as_proxy(upstream_url)
    proxy.add_middleware(CondenserMiddleware(tools_allowlist, toon_only_allowlist, toon_fallback))

    print(f"MCP condenser proxy starting on {host}:{port}", file=sys.stderr)
    print(f"  upstream: {upstream_url}", file=sys.stderr)
    print(f"  condensing: {condense_tools_env}", file=sys.stderr)
    print(f"  toon-only: {toon_only_env or '(none)'}", file=sys.stderr)
    print(f"  toon-fallback: {toon_fallback}", file=sys.stderr)

    proxy.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
