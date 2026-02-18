"""
mcp_proxy.py — MCP proxy that condenses JSON/YAML tool responses via condenser.

Sits between an agent and an upstream MCP server, intercepting tool responses
and compressing verbose JSON (e.g. Kubernetes API output) into compact TOON text.

Configuration (environment variables):
    UPSTREAM_MCP_URL    — URL of the upstream MCP server (required)
    CONDENSE_TOOLS      — comma-separated tool names, or * for all (default: *)
    TOON_ONLY_TOOLS     — comma-separated tool names for direct JSON→TOON
                           encoding without semantic preprocessing (default: empty)
    TOON_FALLBACK       — when true, JSON results from tools not in either list
                           are still converted to TOON (default: true)
    MIN_TOKEN_THRESHOLD — skip condensing if original response is below this
                           token count (default: 0 = off)
    REVERT_IF_LARGER    — when true, keep the original response if the condensed
                           output has more tokens than the original (default: false)
    MAX_TOKEN_LIMIT     — global default token cap for all tool responses
                           (default: 0 = off / no limit)
    TOOL_TOKEN_LIMITS   — comma-separated tool_name:limit pairs for per-tool
                           token limit overrides (default: empty)
    PROXY_HOST          — bind host (default: 0.0.0.0)
    PROXY_PORT          — bind port (default: 9000)

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

from condenser import condense_json, toon_encode_json, stats, count_tokens, parse_input, truncate_to_token_limit


class CondenserMiddleware(Middleware):
    """Intercepts tool call responses and condenses JSON into TOON text."""

    def __init__(
        self,
        tools_allowlist: set[str] | None = None,
        toon_only_allowlist: set[str] | None = None,
        toon_fallback: bool = True,
        min_token_threshold: int = 0,
        revert_if_larger: bool = False,
        max_token_limit: int = 0,
        tool_token_limits: dict[str, int] | None = None,
    ):
        """
        Args:
            tools_allowlist: Set of tool names for full condensing, or None for all.
            toon_only_allowlist: Set of tool names for direct TOON encoding (no preprocessing).
            toon_fallback: When True, JSON from unmatched tools is still TOON-encoded.
            min_token_threshold: Skip condensing if original is below this token count (0 = off).
            revert_if_larger: When True, keep original if condensed has more tokens.
            max_token_limit: Global default token cap for all tool responses (0 = off).
            tool_token_limits: Per-tool token limit overrides {tool_name: limit}.
        """
        super().__init__()
        self.tools_allowlist = tools_allowlist
        self.toon_only_allowlist = toon_only_allowlist or set()
        self.toon_fallback = toon_fallback
        self.min_token_threshold = min_token_threshold
        self.revert_if_larger = revert_if_larger
        self.max_token_limit = max_token_limit
        self.tool_token_limits = tool_token_limits or {}

    def _should_process(self, tool_name: str) -> bool:
        """Check if a tool should be processed by any condensing path."""
        if tool_name in self.toon_only_allowlist:
            return True
        if self.tools_allowlist is None or tool_name in self.tools_allowlist:
            return True
        if self.toon_fallback:
            return True
        return False

    async def on_list_tools(self, context, call_next):
        tools = await call_next(context)
        # Strip outputSchema from tools we'll condense so the client
        # doesn't expect structuredContent in responses.
        for tool in tools:
            if self._should_process(tool.name):
                tool.output_schema = None
        return tools

    async def on_call_tool(self, context, call_next) -> ToolResult:
        tool_name = context.message.name
        result = await call_next(context)

        condensed_any = False
        for item in result.content:
            if not isinstance(item, TextContent):
                continue
            try:
                data, input_fmt = parse_input(item.text)
            except ValueError:
                continue

            orig_text = item.text
            orig_tokens = count_tokens(orig_text)

            # Check minimum token threshold — skip if below
            if self.min_token_threshold > 0 and orig_tokens < self.min_token_threshold:
                print(
                    f"[condenser] {tool_name}: skipped — "
                    f"{orig_tokens:,} tokens below threshold "
                    f"({self.min_token_threshold:,})",
                    file=sys.stderr,
                )
                continue

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

            s = stats(orig_text, condensed, orig_tok=orig_tokens)

            # Revert if condensed is larger than original
            if self.revert_if_larger and s["cond_tok"] >= s["orig_tok"]:
                print(
                    f"[condenser] {tool_name} ({mode}): reverted — "
                    f"condensed {s['cond_tok']:,} tokens >= "
                    f"original {s['orig_tok']:,} tokens",
                    file=sys.stderr,
                )
                continue

            item.text = condensed
            condensed_any = True

            print(
                f"[condenser] {tool_name} ({mode}, {input_fmt}): "
                f"{s['orig_tok']:,}→{s['cond_tok']:,} tokens "
                f"({s['tok_pct']}% reduction)",
                file=sys.stderr,
            )

        # Clear structuredContent so the client uses our condensed text
        if condensed_any:
            result.structured_content = None

        # Apply token limit truncation as final step
        effective_limit = self.tool_token_limits.get(tool_name, self.max_token_limit)
        if effective_limit > 0:
            for item in result.content:
                if not isinstance(item, TextContent):
                    continue
                truncated = truncate_to_token_limit(item.text, effective_limit)
                if truncated is not item.text:
                    item.text = truncated
                    print(
                        f"[condenser] {tool_name}: truncated to "
                        f"{effective_limit} token limit",
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

    min_token_threshold = int(os.environ.get("MIN_TOKEN_THRESHOLD", "0"))

    revert_if_larger_env = os.environ.get("REVERT_IF_LARGER", "false").strip().lower()
    revert_if_larger = revert_if_larger_env not in ("false", "0", "no")

    max_token_limit = int(os.environ.get("MAX_TOKEN_LIMIT", "0"))

    tool_token_limits_env = os.environ.get("TOOL_TOKEN_LIMITS", "").strip()
    tool_token_limits: dict[str, int] = {}
    if tool_token_limits_env:
        for pair in tool_token_limits_env.split(","):
            pair = pair.strip()
            if ":" in pair:
                name, limit = pair.rsplit(":", 1)
                tool_token_limits[name.strip()] = int(limit.strip())

    host = os.environ.get("PROXY_HOST", "0.0.0.0")
    port = int(os.environ.get("PROXY_PORT", "9000"))

    proxy = FastMCP.as_proxy(upstream_url)
    proxy.add_middleware(CondenserMiddleware(
        tools_allowlist, toon_only_allowlist, toon_fallback,
        min_token_threshold, revert_if_larger,
        max_token_limit, tool_token_limits,
    ))

    print(f"MCP condenser proxy starting on {host}:{port}", file=sys.stderr)
    print(f"  upstream: {upstream_url}", file=sys.stderr)
    print(f"  condensing: {condense_tools_env}", file=sys.stderr)
    print(f"  toon-only: {toon_only_env or '(none)'}", file=sys.stderr)
    print(f"  toon-fallback: {toon_fallback}", file=sys.stderr)
    print(f"  min-token-threshold: {min_token_threshold or 'off'}", file=sys.stderr)
    print(f"  revert-if-larger: {revert_if_larger}", file=sys.stderr)
    print(f"  max-token-limit: {max_token_limit or 'off'}", file=sys.stderr)
    print(f"  tool-token-limits: {tool_token_limits_env or '(none)'}", file=sys.stderr)

    proxy.run(transport="streamable-http", host=host, port=port)


if __name__ == "__main__":
    main()
