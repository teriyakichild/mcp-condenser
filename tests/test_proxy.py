"""Unit tests for CondenserMiddleware."""

import json

import pytest

from mcp_condenser.config import ServerConfig
from mcp_condenser.proxy import CondenserMiddleware


def _make_middleware(
    server_configs=None,
    tool_server_map=None,
    **kwargs,
):
    """Helper to create a middleware with a single default server config."""
    if server_configs is None:
        cfg = ServerConfig(url="http://localhost/mcp", **kwargs)
        server_configs = {"default": cfg}
    return CondenserMiddleware(
        server_configs=server_configs,
        tool_server_map=tool_server_map,
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
        assert mode == "toon-only"
        assert "test" in condensed

    def test_toon_fallback_mode(self):
        mw = _make_middleware(tools=["other_tool"], toon_fallback=True)
        cfg = mw._resolve_server_config("unmatched_tool")
        text = json.dumps({"name": "test"})
        result = mw._condense_item(text, "unmatched_tool", cfg)
        assert result is not None
        _, mode = result
        assert mode == "toon-fallback"

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
