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

## CLI usage

Condense a JSON or YAML file:

```bash
uv run python condenser.py input.json
uv run python condenser.py input.yaml
uv run python condenser.py input.json -o out.txt -q
cat pods.yaml | uv run python condenser.py
```

## MCP proxy usage

Run as a proxy between your agent and an upstream MCP server:

```bash
UPSTREAM_MCP_URL=http://localhost:8080/mcp uv run python mcp_proxy.py
```

The proxy intercepts tool call responses, detects JSON payloads, and replaces
them with condensed TOON text before forwarding to the agent.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `UPSTREAM_MCP_URL` | *(required)* | URL of the upstream MCP server |
| `CONDENSE_TOOLS` | `*` | Comma-separated tool names to condense, or `*` for all |
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

See `chart/values.yaml` for all configurable values.

## Development

```bash
uv sync
uv run pytest tests/
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
