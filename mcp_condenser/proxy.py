"""
mcp_proxy.py — MCP proxy that condenses JSON/YAML tool responses via condenser.

Sits between an agent and an upstream MCP server, intercepting tool responses
and compressing verbose JSON (e.g. Kubernetes API output) into compact TOON text.

Supports two modes:
  1. Single-upstream (legacy): UPSTREAM_MCP_URL env var
  2. Multi-upstream: CONDENSER_CONFIG JSON file

Configuration (environment variables — single-upstream mode):
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

Multi-upstream mode (CONDENSER_CONFIG env var → path to JSON config file):
    See config.py / README for config file schema.

Processing order for each JSON tool result:
    1. Tool in TOON_ONLY_TOOLS → toon_format.encode (no preprocessing)
    2. Tool in CONDENSE_TOOLS (or *) → condense_json (full pipeline)
    3. JSON detected and TOON_FALLBACK is true → toon_format.encode
    4. Otherwise → pass through unchanged

Usage:
    UPSTREAM_MCP_URL=http://localhost:8080/mcp python mcp_proxy.py
    CONDENSER_CONFIG=config.json python mcp_proxy.py
"""

import contextlib
import datetime
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import httpx
from fastmcp import FastMCP
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware
from fastmcp.tools.tool import ToolResult
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client
from mcp.types import TextContent
from typing_extensions import Unpack

from mcp_condenser.condenser import Heuristics, condense_json, toon_encode_json, stats, count_tokens, parse_input, truncate_to_token_limit
from mcp_condenser.config import ProxyConfig, ServerConfig
from mcp_condenser.metrics import MetricsRecorder, NoopRecorder, create_recorder, timer


class _ForwardingTransport(StreamableHttpTransport):
    """Transport that selectively forwards and renames incoming request headers.

    When forward_headers is configured, only the mapped headers are forwarded
    from the incoming request (instead of the default forward-everything behavior).
    Static headers from config are always applied on top.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        forward_headers: dict[str, str] | None = None,
    ):
        super().__init__(url, headers=headers)
        self._forward_map = forward_headers or {}

    @contextlib.asynccontextmanager
    async def connect_session(
        self, **session_kwargs: Unpack["StreamableHttpTransport.SessionKwargs"],  # type: ignore[override]
    ) -> AsyncIterator[ClientSession]:
        # Translate incoming headers per the mapping instead of forwarding all
        incoming = get_http_headers()
        translated = {}
        for src, dst in self._forward_map.items():
            val = incoming.get(src.lower())
            if val is not None:
                translated[dst.lower()] = val
        # Static headers override translated headers
        headers = translated | self.headers

        timeout: httpx.Timeout | None = None
        if session_kwargs.get("read_timeout_seconds") is not None:
            read_timeout_seconds = cast(
                datetime.timedelta, session_kwargs.get("read_timeout_seconds")
            )
            timeout = httpx.Timeout(30.0, read=read_timeout_seconds.total_seconds())

        if self.httpx_client_factory is not None:
            http_client = self.httpx_client_factory(
                headers=headers,
                auth=self.auth,
                follow_redirects=True,
                **({"timeout": timeout} if timeout else {}),
            )
        else:
            http_client = create_mcp_http_client(
                headers=headers,
                timeout=timeout,
                auth=self.auth,
            )

        async with (
            http_client,
            streamable_http_client(self.url, http_client=http_client) as transport,
        ):
            read_stream, write_stream, get_session_id = transport
            self._get_session_id_cb = get_session_id
            async with ClientSession(
                read_stream, write_stream, **session_kwargs
            ) as session:
                yield session


def _make_client(srv_cfg: ServerConfig):
    """Create a FastMCP Client with per-upstream headers when configured."""
    from fastmcp.client.client import Client

    if srv_cfg.forward_headers:
        transport = _ForwardingTransport(
            url=srv_cfg.url,
            headers=srv_cfg.headers or None,
            forward_headers=srv_cfg.forward_headers,
        )
        return Client(transport)
    if srv_cfg.headers:
        from fastmcp.client.transports import StreamableHttpTransport

        transport = StreamableHttpTransport(url=srv_cfg.url, headers=srv_cfg.headers)
        return Client(transport)
    return Client(srv_cfg.url)


class CondenserMiddleware(Middleware):
    """Intercepts tool call responses and condenses JSON into TOON text."""

    def __init__(
        self,
        server_configs: dict[str, ServerConfig],
        tool_server_map: dict[str, str] | None = None,
        metrics: MetricsRecorder | None = None,
    ):
        """
        Args:
            server_configs: Map of server name → ServerConfig.
            tool_server_map: Map of tool name → server name. When None,
                uses the first (only) server config for all tools.
            metrics: Metrics recorder (NoopRecorder when None).
        """
        super().__init__()
        self.server_configs = server_configs
        self.tool_server_map = tool_server_map
        self.metrics: MetricsRecorder = metrics or NoopRecorder()

    def _resolve_server_name(self, tool_name: str) -> str:
        """Map a tool name to its server name for metric labels."""
        if self.tool_server_map is not None:
            return self.tool_server_map.get(tool_name, "unknown")
        return next(iter(self.server_configs), "default")

    def _resolve_server_config(self, tool_name: str) -> ServerConfig | None:
        """Map a tool name back to its ServerConfig."""
        if self.tool_server_map is not None:
            server_name = self.tool_server_map.get(tool_name)
            if server_name:
                return self.server_configs.get(server_name)
            return None
        # Single-upstream: return the one config
        if len(self.server_configs) == 1:
            return next(iter(self.server_configs.values()))
        return None

    def _should_process(self, tool_name: str, cfg: ServerConfig) -> bool:
        """Check if a tool should be processed by any condensing path."""
        if not cfg.condense:
            return False
        # Check toon_only list (unprefixed tool name)
        base_name = self._base_tool_name(tool_name)
        if base_name in cfg.toon_only_tools:
            return True
        # Check condense tools allowlist
        if cfg.tools is None or base_name in cfg.tools:
            return True
        if cfg.toon_fallback:
            return True
        return False

    def _base_tool_name(self, tool_name: str) -> str:
        """Strip server prefix from tool name if present."""
        if self.tool_server_map and tool_name in self.tool_server_map:
            server_name = self.tool_server_map[tool_name]
            prefix = f"{server_name}_"
            if tool_name.startswith(prefix):
                return tool_name[len(prefix):]
        return tool_name

    def _condense_item(self, text: str, tool_name: str, cfg: ServerConfig) -> tuple[str, str] | None:
        """Apply condensing to a single text item.

        Returns (condensed_text, mode) or None if no condensing was applied.
        """
        server_name = self._resolve_server_name(tool_name)

        try:
            data, input_fmt = parse_input(text)
        except ValueError:
            self.metrics.record_request(tool_name, server_name, "passthrough")
            return None

        orig_tokens = count_tokens(text)

        # Check minimum token threshold
        if cfg.min_token_threshold > 0 and orig_tokens < cfg.min_token_threshold:
            print(
                f"[condenser] {tool_name}: skipped — "
                f"{orig_tokens:,} tokens below threshold "
                f"({cfg.min_token_threshold:,})",
                file=sys.stderr,
            )
            self.metrics.record_request(tool_name, server_name, "skipped")
            return None

        base_name = self._base_tool_name(tool_name)

        # Build heuristics from config, merging tool-specific overrides
        merged = dict(cfg.heuristics)
        merged.update(cfg.tool_heuristics.get(base_name, {}))
        if merged:
            try:
                h = Heuristics(**merged)
            except TypeError as exc:
                valid_keys = ", ".join(f.name for f in Heuristics.__dataclass_fields__.values())
                raise TypeError(
                    f"Invalid heuristics configuration {merged!r}: {exc}. "
                    f"Valid heuristic names are: {valid_keys}"
                ) from exc
        else:
            h = None

        # 1. TOON_ONLY → direct TOON encoding
        if base_name in cfg.toon_only_tools:
            condensed = toon_encode_json(data)
            mode = "toon_only"
        # 2. CONDENSE (or *) → full pipeline
        elif cfg.tools is None or base_name in cfg.tools:
            condensed = condense_json(data, heuristics=h)
            mode = "condense"
        # 3. TOON_FALLBACK → direct TOON encoding
        elif cfg.toon_fallback:
            condensed = toon_encode_json(data)
            mode = "toon_fallback"
        # 4. No match
        else:
            self.metrics.record_request(tool_name, server_name, "passthrough")
            return None

        s = stats(text, condensed, orig_tok=orig_tokens)

        # Revert if condensed is larger
        if cfg.revert_if_larger and s["cond_tok"] >= s["orig_tok"]:
            print(
                f"[condenser] {tool_name} ({mode}): reverted — "
                f"condensed {s['cond_tok']:,} tokens >= "
                f"original {s['orig_tok']:,} tokens",
                file=sys.stderr,
            )
            self.metrics.record_request(tool_name, server_name, "reverted")
            return None

        print(
            f"[condenser] {tool_name} ({mode}, {input_fmt}): "
            f"{s['orig_tok']:,}→{s['cond_tok']:,} tokens "
            f"({s['tok_pct']}% reduction)",
            file=sys.stderr,
        )

        self.metrics.record_request(tool_name, server_name, mode)
        self.metrics.record_tokens(tool_name, server_name, s["orig_tok"], s["cond_tok"])
        if s["orig_tok"] > 0:
            self.metrics.record_compression_ratio(
                tool_name, server_name, s["cond_tok"] / s["orig_tok"]
            )

        return condensed, mode

    async def on_list_tools(self, context, call_next):
        tools = await call_next(context)
        for tool in tools:
            cfg = self._resolve_server_config(tool.name)
            if cfg and self._should_process(tool.name, cfg):
                tool.output_schema = None
        return tools

    async def on_call_tool(self, context, call_next) -> ToolResult:
        tool_name = context.message.name
        result = await call_next(context)

        cfg = self._resolve_server_config(tool_name)
        if not cfg or not cfg.condense:
            server_name = self._resolve_server_name(tool_name)
            self.metrics.record_request(tool_name, server_name, "passthrough")
            return result

        server_name = self._resolve_server_name(tool_name)

        condensed_any = False
        for item in result.content:
            if not isinstance(item, TextContent):
                continue

            with timer() as elapsed:
                condensed_result = self._condense_item(item.text, tool_name, cfg)
            self.metrics.record_processing_seconds(tool_name, server_name, elapsed())

            if condensed_result is not None:
                item.text = condensed_result[0]
                condensed_any = True

        # Clear structuredContent so the client uses our condensed text
        if condensed_any:
            result.structured_content = None

        # Apply token limit truncation as final step
        base_name = self._base_tool_name(tool_name)
        effective_limit = cfg.tool_token_limits.get(base_name, cfg.max_token_limit)
        if effective_limit > 0:
            for item in result.content:
                if not isinstance(item, TextContent):
                    continue
                truncated = truncate_to_token_limit(item.text, effective_limit)
                if truncated is not item.text:
                    item.text = truncated
                    self.metrics.record_truncation(tool_name, server_name)
                    print(
                        f"[condenser] {tool_name}: truncated to "
                        f"{effective_limit} token limit",
                        file=sys.stderr,
                    )

        return result


def main():
    config = ProxyConfig.load()
    metrics = create_recorder(enabled=config.metrics_enabled, port=config.metrics_port)

    if config.multi_upstream:
        _run_multi_upstream(config, metrics)
    else:
        _run_single_upstream(config, metrics)


def _run_single_upstream(config: ProxyConfig, metrics: MetricsRecorder):
    """Single-upstream mode: same as legacy behavior."""
    srv_cfg = config.servers["default"]

    proxy = FastMCP.as_proxy(_make_client(srv_cfg))
    proxy.add_middleware(CondenserMiddleware(
        server_configs=config.servers,
        metrics=metrics,
    ))

    condense_tools_desc = "*" if srv_cfg.tools is None else ",".join(srv_cfg.tools)
    toon_only_desc = ",".join(srv_cfg.toon_only_tools) or "(none)"

    print(f"MCP condenser proxy starting on {config.host}:{config.port}", file=sys.stderr)
    print(f"  upstream: {srv_cfg.url}", file=sys.stderr)
    print(f"  condensing: {condense_tools_desc}", file=sys.stderr)
    print(f"  toon-only: {toon_only_desc}", file=sys.stderr)
    print(f"  toon-fallback: {srv_cfg.toon_fallback}", file=sys.stderr)
    print(f"  min-token-threshold: {srv_cfg.min_token_threshold or 'off'}", file=sys.stderr)
    print(f"  revert-if-larger: {srv_cfg.revert_if_larger}", file=sys.stderr)
    print(f"  max-token-limit: {srv_cfg.max_token_limit or 'off'}", file=sys.stderr)
    ttl_desc = ",".join(f"{k}:{v}" for k, v in srv_cfg.tool_token_limits.items()) or "(none)"
    print(f"  tool-token-limits: {ttl_desc}", file=sys.stderr)
    if config.metrics_enabled:
        print(f"  metrics: http://0.0.0.0:{config.metrics_port}/metrics", file=sys.stderr)

    proxy.run(transport="streamable-http", host=config.host, port=config.port)


def _run_multi_upstream(config: ProxyConfig, metrics: MetricsRecorder):
    """Multi-upstream mode: aggregate tools from multiple upstreams."""
    from fastmcp.server.proxy import ProxyTool

    tool_server_map: dict[str, str] = {}
    prefix_tools = config.prefix_tools

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[None]:
        for server_name, srv_cfg in config.servers.items():
            client = _make_client(srv_cfg)
            async with client:
                mcp_tools = await client.list_tools()

            for mcp_tool in mcp_tools:
                # Filter by allowlist
                if srv_cfg.tools is not None and mcp_tool.name not in srv_cfg.tools:
                    continue

                if prefix_tools:
                    registered_name = f"{server_name}_{mcp_tool.name}"
                else:
                    registered_name = mcp_tool.name
                    # Collision detection when prefixing is disabled
                    if registered_name in tool_server_map:
                        existing_server = tool_server_map[registered_name]
                        raise ValueError(
                            f"Tool name collision: '{registered_name}' is provided by "
                            f"both '{existing_server}' and '{server_name}'. "
                            f"Enable prefix_tools or use the 'tools' allowlist to resolve."
                        )

                # Create a new Client for each ProxyTool (they manage their own sessions)
                tool_client = _make_client(srv_cfg)
                proxy_tool = ProxyTool.from_mcp_tool(tool_client, mcp_tool)
                # ProxyTool is a pydantic model — create a copy with the registered name
                proxy_tool = proxy_tool.model_copy(update={"name": registered_name})
                server.add_tool(proxy_tool)
                tool_server_map[registered_name] = server_name

                print(
                    f"  registered: {registered_name} (from {server_name})",
                    file=sys.stderr,
                )

        yield

    app = FastMCP(
        name="mcp-condenser",
        lifespan=lifespan,
    )
    app.add_middleware(CondenserMiddleware(
        server_configs=config.servers,
        tool_server_map=tool_server_map,
        metrics=metrics,
    ))

    print(f"MCP condenser proxy starting on {config.host}:{config.port}", file=sys.stderr)
    print(f"  mode: multi-upstream ({len(config.servers)} servers)", file=sys.stderr)
    print(f"  prefix-tools: {config.prefix_tools}", file=sys.stderr)
    for name, srv_cfg in config.servers.items():
        tools_desc = "*" if srv_cfg.tools is None else ",".join(srv_cfg.tools)
        print(f"  [{name}] {srv_cfg.url} — tools: {tools_desc}, condense: {srv_cfg.condense}", file=sys.stderr)
    if config.metrics_enabled:
        print(f"  metrics: http://0.0.0.0:{config.metrics_port}/metrics", file=sys.stderr)

    app.run(transport="streamable-http", host=config.host, port=config.port)


if __name__ == "__main__":
    main()
