"""Configuration for mcp-condenser proxy.

Supports two modes:
  1. Legacy single-upstream via UPSTREAM_MCP_URL + env vars
  2. Multi-upstream via CONDENSER_CONFIG JSON file
"""

import json
import os
import sys
from dataclasses import dataclass, field


@dataclass
class ServerConfig:
    """Per-upstream server configuration."""

    url: str
    tools: list[str] | None = None  # None means all ("*")
    headers: dict[str, str] = field(default_factory=dict)
    forward_headers: dict[str, str] = field(default_factory=dict)
    condense: bool = True
    toon_only_tools: list[str] = field(default_factory=list)
    toon_fallback: bool = True
    min_token_threshold: int = 0
    revert_if_larger: bool = False
    max_token_limit: int = 0
    tool_token_limits: dict[str, int] = field(default_factory=dict)
    heuristics: dict[str, bool | int] = field(default_factory=dict)


@dataclass
class ProxyConfig:
    """Full proxy configuration."""

    servers: dict[str, ServerConfig]
    host: str = "0.0.0.0"
    port: int = 9000
    multi_upstream: bool = False
    prefix_tools: bool = True
    metrics_enabled: bool = False
    metrics_port: int = 9090

    @classmethod
    def from_env(cls) -> "ProxyConfig":
        """Build config from legacy env vars (single-upstream mode)."""
        url = os.environ.get("UPSTREAM_MCP_URL")
        if not url:
            print("error: UPSTREAM_MCP_URL environment variable is required", file=sys.stderr)
            sys.exit(1)

        condense_tools_env = os.environ.get("CONDENSE_TOOLS", "*").strip()
        if condense_tools_env == "*":
            tools = None
        else:
            tools = [t.strip() for t in condense_tools_env.split(",") if t.strip()]

        toon_only_env = os.environ.get("TOON_ONLY_TOOLS", "").strip()
        toon_only = [t.strip() for t in toon_only_env.split(",") if t.strip()] if toon_only_env else []

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

        heuristics_env = os.environ.get("CONDENSER_HEURISTICS", "").strip()
        heuristics: dict[str, bool | int] = {}
        if heuristics_env:
            for pair in heuristics_env.split(","):
                pair = pair.strip()
                if ":" in pair:
                    name, val = pair.rsplit(":", 1)
                    val = val.strip()
                    try:
                        heuristics[name.strip()] = int(val)
                    except ValueError:
                        heuristics[name.strip()] = val.lower() not in ("false", "0", "no")

        host = os.environ.get("PROXY_HOST", "0.0.0.0")
        port = int(os.environ.get("PROXY_PORT", "9000"))

        metrics_enabled_env = os.environ.get("METRICS_ENABLED", "false").strip().lower()
        metrics_enabled = metrics_enabled_env not in ("false", "0", "no", "")
        metrics_port = int(os.environ.get("METRICS_PORT", "9090"))

        headers_env = os.environ.get("UPSTREAM_MCP_HEADERS", "").strip()
        headers: dict[str, str] = {}
        if headers_env:
            headers = json.loads(headers_env)

        server = ServerConfig(
            url=url,
            tools=tools,
            headers=headers,
            condense=True,
            toon_only_tools=toon_only,
            toon_fallback=toon_fallback,
            min_token_threshold=min_token_threshold,
            revert_if_larger=revert_if_larger,
            max_token_limit=max_token_limit,
            tool_token_limits=tool_token_limits,
            heuristics=heuristics,
        )
        return cls(
            servers={"default": server},
            host=host,
            port=port,
            multi_upstream=False,
            metrics_enabled=metrics_enabled,
            metrics_port=metrics_port,
        )

    @classmethod
    def from_file(cls, path: str) -> "ProxyConfig":
        """Load config from a JSON file (multi-upstream mode)."""
        with open(path) as f:
            raw = json.load(f)

        global_cfg = raw.get("global", {})
        host = global_cfg.get("host", "0.0.0.0")
        port = global_cfg.get("port", 9000)
        prefix_tools = global_cfg.get("prefix_tools", True)
        metrics_enabled_default = os.environ.get("METRICS_ENABLED", "false").strip().lower() not in ("false", "0", "no", "")
        metrics_enabled = global_cfg.get("metrics_enabled", metrics_enabled_default)
        metrics_port = global_cfg.get("metrics_port", int(os.environ.get("METRICS_PORT", "9090")))

        servers: dict[str, ServerConfig] = {}
        for name, srv in raw.get("servers", {}).items():
            tools_val = srv.get("tools", "*")
            if tools_val == "*":
                tools = None
            else:
                tools = list(tools_val)

            toon_only = srv.get("toon_only_tools", [])
            tool_token_limits = {k: int(v) for k, v in srv.get("tool_token_limits", {}).items()}
            srv_heuristics = srv.get("heuristics", {})

            servers[name] = ServerConfig(
                url=srv["url"],
                tools=tools,
                headers=srv.get("headers", {}),
                forward_headers=srv.get("forward_headers", {}),
                condense=srv.get("condense", True),
                toon_only_tools=toon_only,
                toon_fallback=srv.get("toon_fallback", True),
                min_token_threshold=srv.get("min_token_threshold", 0),
                revert_if_larger=srv.get("revert_if_larger", False),
                max_token_limit=srv.get("max_token_limit", 0),
                tool_token_limits=tool_token_limits,
                heuristics=srv_heuristics,
            )

        return cls(
            servers=servers,
            host=host,
            port=port,
            multi_upstream=True,
            prefix_tools=prefix_tools,
            metrics_enabled=metrics_enabled,
            metrics_port=metrics_port,
        )

    @classmethod
    def load(cls) -> "ProxyConfig":
        """Load config: CONDENSER_CONFIG file takes priority, falls back to env vars."""
        config_path = os.environ.get("CONDENSER_CONFIG")
        if config_path:
            return cls.from_file(config_path)
        return cls.from_env()
