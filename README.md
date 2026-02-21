# mcp-condenser

MCP proxy that condenses verbose JSON and YAML tool responses into compact
[TOON](https://github.com/toon-format/spec) text, dramatically reducing token
usage for API outputs that return many records with the same nested schema —
pod listings, node status tables, cloud resource inventories, and similar.

## How it works

1. **Flatten** nested objects into dot-notation keys (`spec.containers.0.image`).
2. **Tabulate** lists of same-shaped records into compact TOON tables.
3. **Condense** columns that repeat the same signal: zero-values, nulls, constants,
   and timestamps within the same 60-second window are summarized once rather
   than repeated per row.
4. **Group** related keys (e.g. `requests.cpu`, `requests.memory`) into
   compact combined columns.

The result is a human-readable, LLM-friendly text representation that typically
achieves 60-80% token reduction on real-world API responses.

## Quick start

```bash
docker run -p 9000:9000 \
  -e UPSTREAM_MCP_URL=http://host.docker.internal:8080/mcp \
  teriyakichild/mcp-condenser:0.4.2
```

Point your MCP client at `http://localhost:9000/mcp`.

> `host.docker.internal` resolves to the host machine on Docker Desktop
> (macOS/Windows). On Linux, add `--add-host=host.docker.internal:host-gateway`
> or use the upstream's real address.

## MCP proxy usage

To run from source instead of Docker:

### Single upstream (env vars)

Set `UPSTREAM_MCP_URL` and optionally tune behavior with the environment
variables listed in the [configuration reference](#configuration-reference)
below.

```bash
UPSTREAM_MCP_URL=http://localhost:8080/mcp uv run mcp-condenser-proxy
```

### Multi-upstream (config file)

Aggregate multiple MCP servers behind one endpoint using a JSON config file.
Each server block specifies its URL, which tools to expose, per-server
condensing toggles, and authentication headers (static or forwarded from the
client).

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
| `TOON_FALLBACK` | `true` | Apply basic TOON encoding to tool responses not covered by `CONDENSE_TOOLS` |
| `MIN_TOKEN_THRESHOLD` | `0` | Skip condensing below this token count (0 = off) |
| `REVERT_IF_LARGER` | `false` | Keep original if condensed is larger |
| `MAX_TOKEN_LIMIT` | `0` | Global token cap (0 = off) |
| `TOOL_TOKEN_LIMITS` | *(empty)* | `tool:limit` pairs (comma-separated) |
| `PROXY_HOST` | `0.0.0.0` | Bind host |
| `PROXY_PORT` | `9000` | Bind port |

### Config file (multi-upstream mode)

Each server block supports tool filtering (`tools`), a per-server condense
toggle (`condense`), static headers (`headers`), and selective header forwarding
from the client (`forward_headers`). See
[`examples/docker-compose/config.json`](examples/docker-compose/config.json)
for the full schema and
[`helm/mcp-condenser/values.yaml`](helm/mcp-condenser/values.yaml) for the
Helm equivalents.

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

The full pipeline consistently achieves 57-73% token reduction on responses
with repeated structure. Run the benchmarks yourself:

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
