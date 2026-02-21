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

## Quick start

```bash
docker run -e UPSTREAM_MCP_URL=http://host.docker.internal:8080/mcp \
  teriyakichild/mcp-condenser:0.4.2
```

Point your MCP client at `http://localhost:9000/mcp`.

## MCP proxy usage

### Single upstream (env vars)

Set `UPSTREAM_MCP_URL` and optionally tune behaviour with the environment
variables listed in the [configuration reference](#configuration-reference)
below.

```bash
UPSTREAM_MCP_URL=http://localhost:8080/mcp uv run mcp-condenser-proxy
```

### Multi-upstream (config file)

Aggregate multiple MCP servers behind one endpoint using a JSON config file.
Each server block specifies its URL, which tools to expose, condensing options,
and optional authentication headers (static or forwarded).

```bash
CONDENSER_CONFIG=config.json uv run mcp-condenser-proxy
```

Tool names are prefixed with the server name by default (e.g. `k8s_get_pods`).
Set `"prefix_tools": false` in the `global` section to disable prefixing.

See [`examples/docker-compose/config.json`](examples/docker-compose/config.json)
for a complete multi-upstream config example.

## Docker Compose

Ready-to-use Compose files for single- and multi-upstream modes are in
[`examples/docker-compose/`](examples/docker-compose/).

## Helm

A Helm chart is included under `helm/mcp-condenser/`:

```bash
helm install mcp-condenser ./helm/mcp-condenser \
  --set config.upstreamMcpUrl=http://upstream:8080/mcp
```

See [`examples/helm/`](examples/helm/) for values files and a Helmfile example,
and [`helm/mcp-condenser/values.yaml`](helm/mcp-condenser/values.yaml) for all
configurable chart values.

## Configuration reference

### Environment variables (single-upstream mode)

| Variable | Default | Description |
|---|---|---|
| `UPSTREAM_MCP_URL` | *(required)* | URL of the upstream MCP server |
| `UPSTREAM_MCP_HEADERS` | *(empty)* | JSON object of headers to send upstream |
| `CONDENSE_TOOLS` | `*` | Comma-separated tool names to condense, or `*` for all |
| `TOON_ONLY_TOOLS` | *(empty)* | Comma-separated tool names for direct TOON encoding |
| `TOON_FALLBACK` | `true` | TOON-encode unmatched JSON results |
| `MIN_TOKEN_THRESHOLD` | `0` | Skip condensing below this token count (0 = off) |
| `REVERT_IF_LARGER` | `false` | Keep original if condensed is larger |
| `MAX_TOKEN_LIMIT` | `0` | Global token cap (0 = off) |
| `TOOL_TOKEN_LIMITS` | *(empty)* | `tool:limit` pairs (comma-separated) |
| `PROXY_HOST` | `0.0.0.0` | Bind host |
| `PROXY_PORT` | `9000` | Bind port |

### Config file (multi-upstream mode)

Global and per-server options are documented in the config example at
[`examples/docker-compose/config.json`](examples/docker-compose/config.json)
and in [`helm/mcp-condenser/values.yaml`](helm/mcp-condenser/values.yaml).

## CLI usage

Condense a JSON or YAML file directly:

```bash
uv run mcp-condenser input.json
uv run mcp-condenser input.yaml
cat pods.yaml | uv run mcp-condenser
```

## Benchmark results

Measured on real Kubernetes API responses using `tiktoken/cl100k_base`:

| Sample | Size | Original | Condensed | Reduction |
|---|---|---|---|---|
| K8s node stats | 30 KB | 9,876 tok | 3,638 tok | **63.2%** |
| K8s node+pod stats | 227 KB | 69,885 tok | 19,151 tok | **72.6%** |
| Wrapped K8s response | 116 KB | 45,224 tok | 19,151 tok | **57.7%** |

```bash
uv run pytest tests/test_benchmark.py -v -s
```

## Development

```bash
uv sync
uv run pytest tests/ -v
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
