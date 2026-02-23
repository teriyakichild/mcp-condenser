# mcp-condenser

[![CI](https://github.com/logdna/mcp-condenser/actions/workflows/ci.yml/badge.svg)](https://github.com/logdna/mcp-condenser/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/logdna/mcp-condenser)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org)
[![GitHub Release](https://img.shields.io/github/v/release/logdna/mcp-condenser)](https://github.com/logdna/mcp-condenser/releases)
[![Docker](https://img.shields.io/docker/v/teriyakichild/mcp-condenser?label=docker)](https://hub.docker.com/r/teriyakichild/mcp-condenser)

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
  teriyakichild/mcp-condenser:latest
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

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for the full reference,
including all environment variables, config file schema, condensing heuristics,
and Helm chart values.

Quick links:
- [Single-upstream mode (env vars)](docs/CONFIGURATION.md#single-upstream-mode-environment-variables)
- [Multi-upstream mode (config file)](docs/CONFIGURATION.md#multi-upstream-mode-config-file)
- [Condensing heuristics](docs/CONFIGURATION.md#heuristics)
- [Helm chart values](docs/CONFIGURATION.md#helm-chart)

## CLI usage

Condense a JSON or YAML file directly:

```bash
uv run mcp-condenser input.json
uv run mcp-condenser input.yaml
cat pods.yaml | uv run mcp-condenser
```

## Benchmark results

### Token reduction

Measured across Kubernetes, AWS, and database fixtures using
`tiktoken/cl100k_base`:

| Fixture | Domain | JSON tokens | TOON tokens | Reduction |
|---------|--------|-------------|-------------|-----------|
| K8s 16-pod node | Kubernetes | 9,876 | 3,656 | **63.0%** |
| K8s 6-pod node | Kubernetes | 15,285 | 5,919 | **61.3%** |
| K8s 30-pod node | Kubernetes | 69,885 | 22,229 | **68.2%** |
| EC2 instances | AWS | 33,498 | 4,386 | **86.9%** |
| SQL orders | Database | 26,165 | 11,298 | **56.8%** |

Compression is domain-agnostic: Kubernetes pod listings, AWS EC2
describe-instances responses, and SQL result sets all benefit, with reductions
ranging from 57% to 87%.

### LLM accuracy

Run the accuracy benchmark against a local Ollama instance to verify TOON
preserves answer quality:

```bash
# Single model
uv run python benchmarks/accuracy.py --model qwen3:4b --host http://localhost:11434

# Multi-model matrix (generates markdown tables)
uv run python benchmarks/matrix.py --host http://localhost:11434
```

The benchmark suite tests 90 questions across 5 fixtures (Kubernetes, AWS EC2,
SQL) covering direct lookups, cross-reference queries, aggregations, and
multi-hop reasoning.

### Local models: context window enablement

Small context windows (8K-64K) common with local models can't fit large API
responses as raw JSON. TOON condensing brings them within reach.

| Fixture | JSON tok | TOON tok | 8K | 16K | 32K | 64K | 128K |
|---------|----------|----------|-----|-----|-----|-----|------|
| K8s 16-pod node | 9,876 | 3,656 | Neither | **TOON only** | JSON + TOON | JSON + TOON | JSON + TOON |
| K8s 6-pod node | 15,285 | 5,919 | Neither | Neither | **TOON only** | JSON + TOON | JSON + TOON |
| EC2 instances | 33,498 | 4,386 | Neither | **TOON only** | **TOON only** | **TOON only** | JSON + TOON |
| SQL orders | 26,165 | 11,298 | Neither | Neither | Neither | **TOON only** | JSON + TOON |
| K8s 30-pod node | 69,885 | 22,229 | Neither | Neither | Neither | Neither | **TOON only** |

Run the token reduction tests (no Ollama required):

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
