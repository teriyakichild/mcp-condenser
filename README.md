# mcp-condenser

MCP proxy that condenses verbose JSON and YAML tool responses into compact
[TOON](https://github.com/toon-format/spec) text, dramatically reducing token
usage when LLM agents talk to tool-heavy servers (e.g. Kubernetes, cloud APIs).

## How it works

1. **Flatten** nested JSON objects into dot-notation keys.
2. **Detect** homogeneous arrays of objects and render them as TOON tables.
3. **Elide** zero-value, null, constant, and clustered-timestamp columns.
4. **Collapse** numeric tuples (e.g. `requests.cpu`, `requests.memory`) into
   compact grouped columns.

The result is a human-readable, LLM-friendly text representation that typically
achieves 60-80% token reduction on real-world API responses.

## Benchmark Results

Measured on real Kubernetes API responses using `tiktoken/cl100k_base`:

| Sample | Size | Original | Condensed | Reduction | TOON-only | Reduction |
|---|---|---|---|---|---|---|
| K8s node stats (30K) | 30 KB | 9,876 tok | 3,638 tok | **63.2%** | 7,587 tok | 23.2% |
| K8s node+pod stats (227K) | 227 KB | 69,885 tok | 19,151 tok | **72.6%** | 49,810 tok | 28.7% |
| Wrapped K8s response (116K) | 116 KB | 45,224 tok | 19,151 tok | **57.7%** | 49,810 tok | -10.1% |

The full condense pipeline (flatten + elide + tabulate) consistently achieves
57-73% token reduction. TOON-only encoding (no preprocessing) provides moderate
savings for flat data but can expand deeply nested structures.

Run benchmarks yourself:

```bash
uv run pytest tests/test_benchmark.py -v -s
```

## CLI usage

Condense a JSON or YAML file:

```bash
uv run mcp-condenser input.json
uv run mcp-condenser input.yaml
uv run mcp-condenser input.json -o out.txt -q
cat pods.yaml | uv run mcp-condenser
```

## MCP proxy usage

### Single upstream (simple mode)

Run as a proxy between your agent and an upstream MCP server:

```bash
UPSTREAM_MCP_URL=http://localhost:8080/mcp uv run mcp-condenser-proxy
```

The proxy intercepts tool call responses, detects JSON payloads, and replaces
them with condensed TOON text before forwarding to the agent.

### Multi-upstream mode

Aggregate multiple upstream MCP servers with per-server tool filtering and
condensing settings:

```bash
CONDENSER_CONFIG=config.json uv run mcp-condenser-proxy
```

Example `config.json`:

```json
{
  "servers": {
    "k8s": {
      "url": "http://localhost:8080/mcp",
      "tools": ["get_pods", "get_nodes"],
      "condense": true,
      "toon_only_tools": [],
      "toon_fallback": true
    },
    "github": {
      "url": "http://localhost:8081/mcp",
      "tools": "*",
      "condense": false
    }
  },
  "global": {
    "host": "0.0.0.0",
    "port": 9000
  }
}
```

In multi-upstream mode, tool names are prefixed with the server name
(e.g. `k8s_get_pods`, `github_list_repos`).

#### Per-server config options

| Field | Default | Description |
|---|---|---|
| `url` | *(required)* | URL of the upstream MCP server |
| `tools` | `"*"` | `"*"` for all tools, or a list of tool names to expose |
| `condense` | `true` | Whether to apply condensing to this server's tools |
| `toon_only_tools` | `[]` | Tool names for direct TOON encoding (no preprocessing) |
| `toon_fallback` | `true` | TOON-encode unmatched JSON results |
| `min_token_threshold` | `0` | Skip condensing below this token count (0 = off) |
| `revert_if_larger` | `false` | Keep original if condensed is larger |
| `max_token_limit` | `0` | Token cap for responses (0 = off) |
| `tool_token_limits` | `{}` | Per-tool token limits (`{"tool_name": limit}`) |

### Environment variables (single-upstream mode)

| Variable | Default | Description |
|---|---|---|
| `UPSTREAM_MCP_URL` | *(required)* | URL of the upstream MCP server |
| `CONDENSE_TOOLS` | `*` | Comma-separated tool names to condense, or `*` for all |
| `TOON_ONLY_TOOLS` | *(empty)* | Comma-separated tool names for direct TOON encoding |
| `TOON_FALLBACK` | `true` | TOON-encode unmatched JSON results |
| `MIN_TOKEN_THRESHOLD` | `0` | Skip condensing below this token count |
| `REVERT_IF_LARGER` | `false` | Keep original if condensed is larger |
| `MAX_TOKEN_LIMIT` | `0` | Global token cap (0 = off) |
| `TOOL_TOKEN_LIMITS` | *(empty)* | `tool:limit` pairs (comma-separated) |
| `PROXY_HOST` | `0.0.0.0` | Bind host |
| `PROXY_PORT` | `9000` | Bind port |

## Docker

```bash
docker build -t mcp-condenser .
docker run -e UPSTREAM_MCP_URL=http://host.docker.internal:8080/mcp mcp-condenser
```

## Helm

A Helm chart is included under `chart/`:

```bash
helm install mcp-condenser ./chart \
  --set config.upstreamMcpUrl=http://upstream:8080/mcp
```

For multi-upstream mode, provide a config JSON:

```bash
helm install mcp-condenser ./chart \
  --set-json 'config.condenserConfig={"servers":{"k8s":{"url":"http://k8s:8080/mcp"}}}'
```

See `chart/values.yaml` for all configurable values.

## Development

```bash
uv sync
uv run pytest tests/ -v
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
