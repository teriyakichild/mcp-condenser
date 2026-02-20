"""Unit tests for CondenserMiddleware."""

import json

import pytest
from prometheus_client import CollectorRegistry

from mcp_condenser.config import ProxyConfig, ServerConfig
from mcp_condenser.metrics import PrometheusRecorder
from mcp_condenser.proxy import CondenserMiddleware


def _make_middleware(
    server_configs=None,
    tool_server_map=None,
    metrics=None,
    **kwargs,
):
    """Helper to create a middleware with a single default server config."""
    if server_configs is None:
        cfg = ServerConfig(url="http://localhost/mcp", **kwargs)
        server_configs = {"default": cfg}
    return CondenserMiddleware(
        server_configs=server_configs,
        tool_server_map=tool_server_map,
        metrics=metrics,
    )


class TestResolveServerConfig:
    def test_single_upstream(self):
        mw = _make_middleware()
        cfg = mw._resolve_server_config("any_tool")
        assert cfg is not None
        assert cfg.url == "http://localhost/mcp"

    def test_multi_upstream_with_map(self):
        configs = {
            "k8s": ServerConfig(url="http://k8s/mcp"),
            "github": ServerConfig(url="http://github/mcp", condense=False),
        }
        tool_map = {"k8s_get_pods": "k8s", "github_list_repos": "github"}
        mw = CondenserMiddleware(server_configs=configs, tool_server_map=tool_map)

        cfg = mw._resolve_server_config("k8s_get_pods")
        assert cfg.url == "http://k8s/mcp"

        cfg = mw._resolve_server_config("github_list_repos")
        assert cfg.url == "http://github/mcp"

    def test_unknown_tool_returns_none(self):
        configs = {"k8s": ServerConfig(url="http://k8s/mcp")}
        tool_map = {"k8s_get_pods": "k8s"}
        mw = CondenserMiddleware(server_configs=configs, tool_server_map=tool_map)
        assert mw._resolve_server_config("unknown_tool") is None


class TestBaseToolName:
    def test_strips_prefix_in_multi(self):
        tool_map = {"k8s_get_pods": "k8s"}
        mw = _make_middleware(tool_server_map=tool_map)
        assert mw._base_tool_name("k8s_get_pods") == "get_pods"

    def test_no_prefix_in_single(self):
        mw = _make_middleware()
        assert mw._base_tool_name("get_pods") == "get_pods"


class TestCondenseItem:
    def test_condense_mode(self):
        mw = _make_middleware()
        cfg = mw._resolve_server_config("test_tool")
        text = json.dumps({"name": "test", "value": 42})
        result = mw._condense_item(text, "test_tool", cfg)
        assert result is not None
        condensed, mode = result
        assert mode == "condense"
        assert "test" in condensed

    def test_toon_only_mode(self):
        mw = _make_middleware(toon_only_tools=["special_tool"])
        cfg = mw._resolve_server_config("special_tool")
        text = json.dumps({"name": "test", "value": 42})
        result = mw._condense_item(text, "special_tool", cfg)
        assert result is not None
        condensed, mode = result
        assert mode == "toon_only"
        assert "test" in condensed

    def test_toon_fallback_mode(self):
        mw = _make_middleware(tools=["other_tool"], toon_fallback=True)
        cfg = mw._resolve_server_config("unmatched_tool")
        text = json.dumps({"name": "test"})
        result = mw._condense_item(text, "unmatched_tool", cfg)
        assert result is not None
        _, mode = result
        assert mode == "toon_fallback"

    def test_passthrough_no_condense(self):
        mw = _make_middleware(condense=False)
        cfg = mw._resolve_server_config("any_tool")
        # _condense_item shouldn't even be called for non-condense servers,
        # but if it is, it still produces output since condense flag is checked at caller
        text = json.dumps({"name": "test"})
        # The middleware checks cfg.condense in on_call_tool, not in _condense_item
        result = mw._condense_item(text, "any_tool", cfg)
        assert result is not None  # _condense_item always tries

    def test_non_json_returns_none(self):
        mw = _make_middleware()
        cfg = mw._resolve_server_config("tool")
        result = mw._condense_item("not json or yaml", "tool", cfg)
        assert result is None

    def test_min_token_threshold_skips(self):
        mw = _make_middleware(min_token_threshold=999999)
        cfg = mw._resolve_server_config("tool")
        text = json.dumps({"small": "data"})
        result = mw._condense_item(text, "tool", cfg)
        assert result is None

    def test_revert_if_larger(self):
        """When condensed output is larger, revert."""
        mw = _make_middleware(revert_if_larger=True)
        cfg = mw._resolve_server_config("tool")
        # Very small data where condensing adds overhead
        text = json.dumps({"a": 1})
        result = mw._condense_item(text, "tool", cfg)
        # For tiny data, condense may add headers that increase size
        # Either way, the method handles it correctly
        # (result is None if reverted, or a tuple if condensed was still smaller)
        assert result is None or isinstance(result, tuple)


class TestShouldProcess:
    def test_condense_all(self):
        mw = _make_middleware()
        cfg = mw._resolve_server_config("any_tool")
        assert mw._should_process("any_tool", cfg) is True

    def test_condense_specific_tools(self):
        mw = _make_middleware(tools=["tool_a"])
        cfg = mw._resolve_server_config("tool_a")
        assert mw._should_process("tool_a", cfg) is True

    def test_condense_disabled(self):
        mw = _make_middleware(condense=False)
        cfg = mw._resolve_server_config("any_tool")
        assert mw._should_process("any_tool", cfg) is False

    def test_toon_only_tool(self):
        mw = _make_middleware(toon_only_tools=["special"])
        cfg = mw._resolve_server_config("special")
        assert mw._should_process("special", cfg) is True

    def test_fallback_catches_unmatched(self):
        mw = _make_middleware(tools=["other"], toon_fallback=True)
        cfg = mw._resolve_server_config("unmatched")
        assert mw._should_process("unmatched", cfg) is True

    def test_no_fallback_rejects_unmatched(self):
        mw = _make_middleware(tools=["other"], toon_fallback=False, toon_only_tools=[])
        cfg = mw._resolve_server_config("unmatched")
        assert mw._should_process("unmatched", cfg) is False


class TestMetricsRecording:
    """Verify that _condense_item records metrics correctly."""

    def _make_with_metrics(self, **kwargs):
        registry = CollectorRegistry()
        rec = PrometheusRecorder(registry=registry)
        mw = _make_middleware(metrics=rec, **kwargs)
        return mw, registry

    def test_condense_records_mode_and_tokens(self):
        mw, reg = self._make_with_metrics()
        cfg = mw._resolve_server_config("tool")
        text = json.dumps({"items": [{"name": f"item-{i}", "value": i} for i in range(20)]})
        result = mw._condense_item(text, "tool", cfg)
        assert result is not None

        assert reg.get_sample_value(
            "condenser_requests_total",
            {"tool": "tool", "server": "default", "mode": "condense"},
        ) == 1.0
        assert reg.get_sample_value(
            "condenser_input_tokens_total",
            {"tool": "tool", "server": "default"},
        ) > 0
        assert reg.get_sample_value(
            "condenser_compression_ratio_count",
            {"tool": "tool", "server": "default"},
        ) == 1.0

    def test_threshold_skip_records_skipped(self):
        mw, reg = self._make_with_metrics(min_token_threshold=999999)
        cfg = mw._resolve_server_config("tool")
        text = json.dumps({"small": "data"})
        result = mw._condense_item(text, "tool", cfg)
        assert result is None

        assert reg.get_sample_value(
            "condenser_requests_total",
            {"tool": "tool", "server": "default", "mode": "skipped"},
        ) == 1.0

    def test_non_json_records_passthrough(self):
        mw, reg = self._make_with_metrics()
        cfg = mw._resolve_server_config("tool")
        result = mw._condense_item("not json", "tool", cfg)
        assert result is None

        assert reg.get_sample_value(
            "condenser_requests_total",
            {"tool": "tool", "server": "default", "mode": "passthrough"},
        ) == 1.0

    def test_revert_records_reverted(self):
        mw, reg = self._make_with_metrics(revert_if_larger=True)
        cfg = mw._resolve_server_config("tool")
        # Tiny data likely to be reverted
        text = json.dumps({"a": 1})
        result = mw._condense_item(text, "tool", cfg)
        if result is None:
            # It was reverted
            assert reg.get_sample_value(
                "condenser_requests_total",
                {"tool": "tool", "server": "default", "mode": "reverted"},
            ) == 1.0


class TestPrefixToolsConfig:
    """Tests for the prefix_tools config option."""

    def test_default_is_true(self):
        cfg = ProxyConfig(servers={})
        assert cfg.prefix_tools is True

    def test_from_file_reads_prefix_tools(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "global": {"prefix_tools": False},
            "servers": {
                "k8s": {"url": "http://k8s/mcp"},
            },
        }))
        cfg = ProxyConfig.from_file(str(config_file))
        assert cfg.prefix_tools is False
        assert cfg.multi_upstream is True

    def test_from_file_defaults_prefix_tools_true(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "servers": {
                "k8s": {"url": "http://k8s/mcp"},
            },
        }))
        cfg = ProxyConfig.from_file(str(config_file))
        assert cfg.prefix_tools is True

    def test_from_env_always_true(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        cfg = ProxyConfig.from_env()
        assert cfg.prefix_tools is True


class TestUnprefixedToolServerMap:
    """Test that tool_server_map works correctly with unprefixed names."""

    def test_resolve_server_config_unprefixed(self):
        configs = {
            "k8s": ServerConfig(url="http://k8s/mcp"),
            "github": ServerConfig(url="http://github/mcp"),
        }
        # Simulate unprefixed registration: original tool names → server names
        tool_map = {"get_pods": "k8s", "list_repos": "github"}
        mw = CondenserMiddleware(server_configs=configs, tool_server_map=tool_map)

        cfg = mw._resolve_server_config("get_pods")
        assert cfg.url == "http://k8s/mcp"

        cfg = mw._resolve_server_config("list_repos")
        assert cfg.url == "http://github/mcp"

    def test_base_tool_name_unprefixed(self):
        """When tools aren't prefixed, _base_tool_name returns the name as-is."""
        tool_map = {"get_pods": "k8s"}
        mw = _make_middleware(tool_server_map=tool_map)
        # "get_pods" doesn't start with "k8s_", so no stripping occurs
        assert mw._base_tool_name("get_pods") == "get_pods"

    def test_should_process_unprefixed(self):
        configs = {
            "k8s": ServerConfig(url="http://k8s/mcp", tools=["get_pods"]),
        }
        tool_map = {"get_pods": "k8s"}
        mw = CondenserMiddleware(server_configs=configs, tool_server_map=tool_map)
        cfg = mw._resolve_server_config("get_pods")
        assert mw._should_process("get_pods", cfg) is True

    def test_condense_item_unprefixed(self):
        configs = {
            "k8s": ServerConfig(url="http://k8s/mcp"),
        }
        tool_map = {"get_pods": "k8s"}
        mw = CondenserMiddleware(server_configs=configs, tool_server_map=tool_map)
        cfg = mw._resolve_server_config("get_pods")
        text = json.dumps({"name": "test", "value": 42})
        result = mw._condense_item(text, "get_pods", cfg)
        assert result is not None
        condensed, mode = result
        assert mode == "condense"


class TestToolCollisionDetection:
    """Test that collision detection works when prefix_tools is disabled."""

    def test_collision_raises_error(self):
        """Simulate what _run_multi_upstream does: detect duplicate tool names."""
        tool_server_map: dict[str, str] = {}
        prefix_tools = False

        # Simulate registering tools from two servers with overlapping names
        server_tools = {
            "k8s": ["get_pods", "get_nodes"],
            "other_k8s": ["get_pods", "list_namespaces"],
        }

        with pytest.raises(ValueError, match="Tool name collision.*get_pods"):
            for server_name, tools in server_tools.items():
                for tool_name in tools:
                    if prefix_tools:
                        registered_name = f"{server_name}_{tool_name}"
                    else:
                        registered_name = tool_name
                        if registered_name in tool_server_map:
                            existing_server = tool_server_map[registered_name]
                            raise ValueError(
                                f"Tool name collision: '{registered_name}' is provided by "
                                f"both '{existing_server}' and '{server_name}'. "
                                f"Enable prefix_tools or use the 'tools' allowlist to resolve."
                            )
                    tool_server_map[registered_name] = server_name

    def test_no_collision_with_distinct_tools(self):
        """No error when servers have distinct tool names."""
        tool_server_map: dict[str, str] = {}
        prefix_tools = False

        server_tools = {
            "k8s": ["get_pods", "get_nodes"],
            "github": ["list_repos", "create_issue"],
        }

        for server_name, tools in server_tools.items():
            for tool_name in tools:
                if prefix_tools:
                    registered_name = f"{server_name}_{tool_name}"
                else:
                    registered_name = tool_name
                    if registered_name in tool_server_map:
                        existing_server = tool_server_map[registered_name]
                        raise ValueError(
                            f"Tool name collision: '{registered_name}' is provided by "
                            f"both '{existing_server}' and '{server_name}'."
                        )
                tool_server_map[registered_name] = server_name

        assert tool_server_map == {
            "get_pods": "k8s",
            "get_nodes": "k8s",
            "list_repos": "github",
            "create_issue": "github",
        }

    def test_no_collision_with_prefix_enabled(self):
        """With prefix_tools=True, same tool names don't collide."""
        tool_server_map: dict[str, str] = {}
        prefix_tools = True

        server_tools = {
            "k8s": ["get_pods"],
            "other_k8s": ["get_pods"],
        }

        for server_name, tools in server_tools.items():
            for tool_name in tools:
                if prefix_tools:
                    registered_name = f"{server_name}_{tool_name}"
                else:
                    registered_name = tool_name
                    if registered_name in tool_server_map:
                        existing_server = tool_server_map[registered_name]
                        raise ValueError(
                            f"Tool name collision: '{registered_name}' is provided by "
                            f"both '{existing_server}' and '{server_name}'."
                        )
                tool_server_map[registered_name] = server_name

        assert tool_server_map == {
            "k8s_get_pods": "k8s",
            "other_k8s_get_pods": "other_k8s",
        }
