"""Tests for config module."""

import json

import pytest

from mcp_condenser.config import ProxyConfig, ServerConfig


class TestFromFile:
    def test_basic(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {
                "k8s": {"url": "http://localhost:8080/mcp"},
                "github": {"url": "http://localhost:8081/mcp", "condense": False},
            }
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert len(config.servers) == 2
        assert config.servers["k8s"].url == "http://localhost:8080/mcp"
        assert config.servers["k8s"].condense is True
        assert config.servers["github"].condense is False
        assert config.multi_upstream is True

    def test_all_options(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {
                "k8s": {
                    "url": "http://localhost:8080/mcp",
                    "tools": ["get_pods", "get_nodes"],
                    "condense": True,
                    "toon_only_tools": ["list_namespaces"],
                    "toon_fallback": False,
                    "min_token_threshold": 100,
                    "revert_if_larger": True,
                    "max_token_limit": 5000,
                    "tool_token_limits": {"get_pods": 3000},
                }
            },
            "global": {"host": "127.0.0.1", "port": 8000},
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        srv = config.servers["k8s"]
        assert srv.tools == ["get_pods", "get_nodes"]
        assert srv.toon_only_tools == ["list_namespaces"]
        assert srv.toon_fallback is False
        assert srv.min_token_threshold == 100
        assert srv.revert_if_larger is True
        assert srv.max_token_limit == 5000
        assert srv.tool_token_limits == {"get_pods": 3000}
        assert config.host == "127.0.0.1"
        assert config.port == 8000

    def test_tools_star_becomes_none(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {"s": {"url": "http://localhost/mcp", "tools": "*"}}
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert config.servers["s"].tools is None

    def test_tools_list_parsed(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {"s": {"url": "http://localhost/mcp", "tools": ["a", "b"]}}
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert config.servers["s"].tools == ["a", "b"]


class TestFromEnv:
    def test_backward_compat(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost:8080/mcp")
        monkeypatch.setenv("CONDENSE_TOOLS", "*")
        monkeypatch.setenv("TOON_ONLY_TOOLS", "tool_a,tool_b")
        monkeypatch.setenv("TOON_FALLBACK", "true")
        monkeypatch.setenv("PROXY_PORT", "8000")
        config = ProxyConfig.from_env()
        assert len(config.servers) == 1
        assert "default" in config.servers
        srv = config.servers["default"]
        assert srv.url == "http://localhost:8080/mcp"
        assert srv.tools is None  # "*" means all
        assert srv.toon_only_tools == ["tool_a", "tool_b"]
        assert srv.toon_fallback is True
        assert config.port == 8000
        assert config.multi_upstream is False

    def test_missing_url_exits(self, monkeypatch):
        monkeypatch.delenv("UPSTREAM_MCP_URL", raising=False)
        monkeypatch.delenv("CONDENSER_CONFIG", raising=False)
        with pytest.raises(SystemExit):
            ProxyConfig.from_env()

    def test_env_parsing(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        monkeypatch.setenv("CONDENSE_TOOLS", "a,b,c")
        monkeypatch.setenv("TOON_FALLBACK", "false")
        monkeypatch.setenv("MIN_TOKEN_THRESHOLD", "500")
        monkeypatch.setenv("REVERT_IF_LARGER", "true")
        monkeypatch.setenv("MAX_TOKEN_LIMIT", "10000")
        monkeypatch.setenv("TOOL_TOKEN_LIMITS", "a:1000,b:2000")
        config = ProxyConfig.from_env()
        srv = config.servers["default"]
        assert srv.tools == ["a", "b", "c"]
        assert srv.toon_fallback is False
        assert srv.min_token_threshold == 500
        assert srv.revert_if_larger is True
        assert srv.max_token_limit == 10000
        assert srv.tool_token_limits == {"a": 1000, "b": 2000}


class TestMetricsConfig:
    def test_defaults(self):
        config = ProxyConfig(servers={})
        assert config.metrics_enabled is False
        assert config.metrics_port == 9090

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        monkeypatch.setenv("METRICS_ENABLED", "true")
        monkeypatch.setenv("METRICS_PORT", "9191")
        config = ProxyConfig.from_env()
        assert config.metrics_enabled is True
        assert config.metrics_port == 9191

    def test_from_env_disabled(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        config = ProxyConfig.from_env()
        assert config.metrics_enabled is False
        assert config.metrics_port == 9090

    def test_from_file(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "global": {"metrics_enabled": True, "metrics_port": 9191},
            "servers": {"s": {"url": "http://localhost/mcp"}},
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert config.metrics_enabled is True
        assert config.metrics_port == 9191

    def test_from_file_defaults(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {"s": {"url": "http://localhost/mcp"}},
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert config.metrics_enabled is False
        assert config.metrics_port == 9090

    def test_from_file_falls_back_to_env(self, tmp_path, monkeypatch):
        """Env vars METRICS_ENABLED / METRICS_PORT are used when the config file omits them."""
        monkeypatch.setenv("METRICS_ENABLED", "true")
        monkeypatch.setenv("METRICS_PORT", "9191")
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {"s": {"url": "http://localhost/mcp"}},
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert config.metrics_enabled is True
        assert config.metrics_port == 9191

    def test_from_file_json_overrides_env(self, tmp_path, monkeypatch):
        """Explicit values in the config file take precedence over env vars."""
        monkeypatch.setenv("METRICS_ENABLED", "true")
        monkeypatch.setenv("METRICS_PORT", "9191")
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "global": {"metrics_enabled": False, "metrics_port": 7777},
            "servers": {"s": {"url": "http://localhost/mcp"}},
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert config.metrics_enabled is False
        assert config.metrics_port == 7777


class TestHeuristicsConfig:
    def test_from_env_parses_heuristics(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        monkeypatch.setenv("CONDENSER_HEURISTICS", "elide_timestamps:false,group_tuples:false")
        config = ProxyConfig.from_env()
        srv = config.servers["default"]
        assert srv.heuristics == {"elide_timestamps": False, "group_tuples": False}

    def test_from_env_true_values(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        monkeypatch.setenv("CONDENSER_HEURISTICS", "elide_all_zero:true,elide_constants:yes")
        config = ProxyConfig.from_env()
        srv = config.servers["default"]
        assert srv.heuristics == {"elide_all_zero": True, "elide_constants": True}

    def test_from_env_empty_default(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        config = ProxyConfig.from_env()
        assert config.servers["default"].heuristics == {}

    def test_from_file_parses_heuristics(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {
                "k8s": {
                    "url": "http://localhost/mcp",
                    "heuristics": {"elide_timestamps": False}
                }
            }
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert config.servers["k8s"].heuristics == {"elide_timestamps": False}

    def test_from_file_empty_default(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {"s": {"url": "http://localhost/mcp"}}
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert config.servers["s"].heuristics == {}


class TestToolHeuristicsConfig:
    def test_from_file_parses_tool_heuristics(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {
                "k8s": {
                    "url": "http://localhost/mcp",
                    "heuristics": {"elide_timestamps": False},
                    "tool_heuristics": {
                        "get_node_metrics": {"elide_constants": False}
                    }
                }
            }
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        srv = config.servers["k8s"]
        assert srv.heuristics == {"elide_timestamps": False}
        assert srv.tool_heuristics == {"get_node_metrics": {"elide_constants": False}}

    def test_from_file_empty_default(self, tmp_path):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {"s": {"url": "http://localhost/mcp"}}
        }))
        config = ProxyConfig.from_file(str(cfg_file))
        assert config.servers["s"].tool_heuristics == {}

    def test_from_env_no_tool_heuristics(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        config = ProxyConfig.from_env()
        assert config.servers["default"].tool_heuristics == {}


class TestStringHeuristicsEnvParsing:
    def test_string_value_preserved(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        monkeypatch.setenv("CONDENSER_HEURISTICS", "some_setting:custom_val,max_table_columns:12")
        config = ProxyConfig.from_env()
        srv = config.servers["default"]
        assert srv.heuristics["some_setting"] == "custom_val"
        assert srv.heuristics["max_table_columns"] == 12

    def test_bool_keywords_still_parsed(self, monkeypatch):
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://localhost/mcp")
        monkeypatch.setenv("CONDENSER_HEURISTICS", "elide_timestamps:false,elide_all_zero:true")
        config = ProxyConfig.from_env()
        srv = config.servers["default"]
        assert srv.heuristics["elide_timestamps"] is False
        assert srv.heuristics["elide_all_zero"] is True


class TestLoad:
    def test_prefers_config_file(self, tmp_path, monkeypatch):
        cfg_file = tmp_path / "config.json"
        cfg_file.write_text(json.dumps({
            "servers": {"s1": {"url": "http://file-url/mcp"}}
        }))
        monkeypatch.setenv("CONDENSER_CONFIG", str(cfg_file))
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://env-url/mcp")
        config = ProxyConfig.load()
        assert config.multi_upstream is True
        assert config.servers["s1"].url == "http://file-url/mcp"

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.delenv("CONDENSER_CONFIG", raising=False)
        monkeypatch.setenv("UPSTREAM_MCP_URL", "http://env-url/mcp")
        config = ProxyConfig.load()
        assert config.multi_upstream is False
        assert config.servers["default"].url == "http://env-url/mcp"
