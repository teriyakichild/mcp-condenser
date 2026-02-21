# Configuration Reference

mcp-condenser supports two configuration modes:

1. **Single-upstream** — environment variables, one upstream MCP server
2. **Multi-upstream** — JSON config file, multiple upstream MCP servers behind one endpoint

## Single-upstream mode (environment variables)

Set `UPSTREAM_MCP_URL` and optionally tune behavior with the variables below.

```bash
UPSTREAM_MCP_URL=http://localhost:8080/mcp uv run mcp-condenser-proxy
```

### Upstream connection

| Variable | Default | Description |
|---|---|---|
| `UPSTREAM_MCP_URL` | *(required)* | URL of the upstream MCP server |
| `UPSTREAM_MCP_HEADERS` | *(empty)* | JSON object of static headers to send upstream (e.g. `'{"Authorization":"Bearer tok"}'`) |

### Tool selection

| Variable | Default | Description |
|---|---|---|
| `CONDENSE_TOOLS` | `*` | Comma-separated tool names to apply the full condensing pipeline to, or `*` for all |
| `TOON_ONLY_TOOLS` | *(empty)* | Comma-separated tool names that skip preprocessing and get direct TOON encoding |
| `TOON_FALLBACK` | `true` | Apply basic TOON encoding to responses not matched by `CONDENSE_TOOLS` or `TOON_ONLY_TOOLS` |

### Token management

| Variable | Default | Description |
|---|---|---|
| `MIN_TOKEN_THRESHOLD` | `0` | Skip condensing if the original response is below this token count (0 = disabled) |
| `REVERT_IF_LARGER` | `false` | Keep the original response if condensed output has more tokens than the input |
| `MAX_TOKEN_LIMIT` | `0` | Global token cap for all tool responses (0 = disabled) |
| `TOOL_TOKEN_LIMITS` | *(empty)* | Per-tool token limits as comma-separated `tool:limit` pairs (e.g. `get_pods:3000,list_nodes:5000`) |

### Condensing heuristics

| Variable | Default | Description |
|---|---|---|
| `CONDENSER_HEURISTICS` | *(empty)* | Toggle individual preprocessing heuristics as comma-separated `key:bool` pairs |

See [Heuristics](#heuristics) below for the full list of heuristic keys.

### Proxy server

| Variable | Default | Description |
|---|---|---|
| `PROXY_HOST` | `0.0.0.0` | IP address to bind to |
| `PROXY_PORT` | `9000` | TCP port to bind to |

### Metrics

| Variable | Default | Description |
|---|---|---|
| `METRICS_ENABLED` | `false` | Enable the Prometheus metrics endpoint |
| `METRICS_PORT` | `9090` | TCP port for the metrics HTTP server |

---

## Multi-upstream mode (config file)

Set `CONDENSER_CONFIG` to the path of a JSON config file. This aggregates
multiple MCP servers behind a single endpoint.

```bash
CONDENSER_CONFIG=config.json uv run mcp-condenser-proxy
```

### Config file schema

```json
{
  "global": {
    "host": "0.0.0.0",
    "port": 9000,
    "prefix_tools": true,
    "metrics_enabled": false,
    "metrics_port": 9090
  },
  "servers": {
    "server_name": {
      "url": "http://upstream:8080/mcp",
      "tools": "*",
      "condense": true,
      "toon_only_tools": [],
      "toon_fallback": true,
      "min_token_threshold": 0,
      "revert_if_larger": false,
      "max_token_limit": 0,
      "tool_token_limits": {},
      "headers": {},
      "forward_headers": {},
      "heuristics": {}
    }
  }
}
```

### Global settings

| Key | Default | Description |
|---|---|---|
| `host` | `0.0.0.0` | Proxy bind host |
| `port` | `9000` | Proxy bind port |
| `prefix_tools` | `true` | Prefix tool names with the server name (e.g. `k8s_get_pods`). Set to `false` to expose original tool names |
| `metrics_enabled` | `false` | Enable Prometheus metrics (falls back to `METRICS_ENABLED` env var) |
| `metrics_port` | `9090` | Metrics port (falls back to `METRICS_PORT` env var) |

### Per-server settings

| Key | Default | Description |
|---|---|---|
| `url` | *(required)* | Upstream MCP server URL |
| `tools` | `"*"` | `"*"` for all tools, or a list of tool names to expose (e.g. `["get_pods", "list_nodes"]`) |
| `condense` | `true` | Enable or disable condensing for this server |
| `toon_only_tools` | `[]` | Tool names that skip preprocessing and get direct TOON encoding |
| `toon_fallback` | `true` | TOON-encode responses not matched by `tools` or `toon_only_tools` |
| `min_token_threshold` | `0` | Skip condensing below this token count |
| `revert_if_larger` | `false` | Keep original if condensed is larger |
| `max_token_limit` | `0` | Token cap for this server's responses |
| `tool_token_limits` | `{}` | Per-tool token limits (e.g. `{"get_pods": 3000}`) |
| `headers` | `{}` | Static headers to send to this upstream |
| `forward_headers` | `{}` | Forward client request headers to upstream. Maps incoming header name to outgoing header name (e.g. `{"Authorization": "X-Custom-Auth"}`) |
| `heuristics` | `{}` | Override individual condensing heuristics (see below) |

---

## Heuristics

Heuristics control the preprocessing steps applied during condensing. All
default to `true`. Disable individual heuristics to preserve specific columns
that would otherwise be elided.

| Key | Default | Description |
|---|---|---|
| `elide_all_zero` | `true` | Remove columns where every value is `0` or empty |
| `elide_all_null` | `true` | Remove columns where every value is `null` or empty |
| `elide_timestamps` | `true` | Collapse timestamps within a 60-second window into a single representative value |
| `elide_constants` | `true` | Remove columns with an identical value across all rows (noted in a header annotation) |
| `group_tuples` | `true` | Group related columns with a shared prefix (e.g. `requests.cpu` + `requests.memory`) into combined columns |

### Setting heuristics via environment variable

```bash
# Disable timestamp elision and tuple grouping
CONDENSER_HEURISTICS="elide_timestamps:false,group_tuples:false"
```

Values are parsed case-insensitively. `false`, `0`, and `no` are treated as
false; everything else is true.

### Setting heuristics via config file

```json
{
  "servers": {
    "k8s": {
      "url": "http://k8s:8080/mcp",
      "heuristics": {
        "elide_timestamps": false,
        "group_tuples": false
      }
    }
  }
}
```

In multi-upstream mode, heuristics are configured per server, so different
upstreams can use different preprocessing strategies.

---

## Helm chart

The Helm chart under `helm/mcp-condenser/` supports all configuration options.

### Single-upstream values

```yaml
config:
  upstreamMcpUrl: "http://upstream:8080/mcp"
  upstreamMcpHeaders: '{"Authorization":"Bearer tok"}'
  condenseTools: "*"
  toonOnlyTools: ""
  toonFallback: "true"
  minTokenThreshold: "0"
  revertIfLarger: "false"
  maxTokenLimit: "0"
  toolTokenLimits: ""
  heuristics: "elide_timestamps:false,group_tuples:false"
  proxyPort: 9000

metrics:
  enabled: false
  port: 9090
```

### Multi-upstream values

Set `config.condenserConfig` to the JSON config content. The chart creates a
ConfigMap and mounts it at `/etc/mcp-condenser/config.json`.

```yaml
config:
  condenserConfig: |
    {
      "servers": {
        "k8s": {
          "url": "http://k8s-mcp:8080/mcp",
          "tools": "*",
          "heuristics": {
            "elide_timestamps": false
          }
        },
        "github": {
          "url": "http://github-mcp:8081/mcp",
          "condense": false,
          "headers": {
            "Authorization": "Bearer ghp_xxxx"
          }
        }
      },
      "global": {
        "prefix_tools": true,
        "metrics_enabled": true,
        "metrics_port": 9090
      }
    }
```

### Additional environment variables

Use `env` to pass arbitrary environment variables not covered by `config.*`:

```yaml
env:
  MY_CUSTOM_VAR: "value"
```

### Metrics and ServiceMonitor

```yaml
metrics:
  enabled: true
  port: 9090
  serviceMonitor:
    enabled: true
    namespace: monitoring
    interval: 30s
    scrapeTimeout: 10s
    labels:
      release: prometheus
```

### Helm values reference

| Value | Default | Maps to |
|---|---|---|
| `config.upstreamMcpUrl` | `""` | `UPSTREAM_MCP_URL` |
| `config.upstreamMcpHeaders` | `""` | `UPSTREAM_MCP_HEADERS` |
| `config.condenseTools` | `"*"` | `CONDENSE_TOOLS` |
| `config.toonOnlyTools` | `""` | `TOON_ONLY_TOOLS` |
| `config.toonFallback` | `"true"` | `TOON_FALLBACK` |
| `config.minTokenThreshold` | `"0"` | `MIN_TOKEN_THRESHOLD` |
| `config.revertIfLarger` | `"false"` | `REVERT_IF_LARGER` |
| `config.maxTokenLimit` | `"0"` | `MAX_TOKEN_LIMIT` |
| `config.toolTokenLimits` | `""` | `TOOL_TOKEN_LIMITS` |
| `config.heuristics` | `""` | `CONDENSER_HEURISTICS` |
| `config.proxyPort` | `9000` | `PROXY_PORT` |
| `config.condenserConfig` | `""` | `CONDENSER_CONFIG` (mounted as file) |
| `metrics.enabled` | `false` | `METRICS_ENABLED` |
| `metrics.port` | `9090` | `METRICS_PORT` |

---

## Boolean parsing

For environment variables, boolean values accept (case-insensitive):

- **True**: any value not listed below
- **False**: `false`, `0`, `no`, or empty/unset

---

## Config loading priority

1. If `CONDENSER_CONFIG` is set, load from file (multi-upstream mode)
2. Otherwise, load from environment variables (single-upstream mode)

In multi-upstream mode, `metrics_enabled` and `metrics_port` fall back to
their environment variable equivalents if not specified in the config file.
