# CHANGELOG


## v0.5.1 (2026-02-21)

### Bug Fixes

- Improve TOON accuracy with cardinality-aware identity columns and tuple size cap
  ([`7becc62`](https://github.com/teriyakichild/mcp-condenser/commit/7becc624beb366f938c5b06e03a0f47c6f424a1f))

- find_identity_column now picks the highest-cardinality column when multiple match the same keyword
  (e.g. podRef.name over network.name) - Add max_tuple_size heuristic (default 4) to prevent large
  positional tuple groups that small LLMs misparse - Support int-valued heuristics in env config
  parser - Add --num-ctx flag to accuracy benchmark for Ollama context control - Add failure logging
  and detail printing to accuracy benchmark

### Documentation

- Add comprehensive configuration reference
  ([`b6fe86b`](https://github.com/teriyakichild/mcp-condenser/commit/b6fe86b8fc7ee06648f472e16650f2996358c56c))

Move inline config tables from README to docs/CONFIGURATION.md covering all env vars, config file
  schema, condensing heuristics, and Helm values.

- Use latest tag instead of hardcoded version in README
  ([`280ec8d`](https://github.com/teriyakichild/mcp-condenser/commit/280ec8dc80fb8baaf1316d2521ce1ee6c51336bb))


## v0.5.0 (2026-02-21)

### Bug Fixes

- Address review feedback on heuristics config
  ([`b115c0a`](https://github.com/teriyakichild/mcp-condenser/commit/b115c0ab46ff0f7f3cb361ae2d6b2ea437568816))

- Wrap Heuristics(**cfg.heuristics) in try/except to surface helpful error on typos listing valid
  key names - Add config parsing tests for CONDENSER_HEURISTICS env var and from_file heuristics
  dict - Add test for invalid heuristic key error message - List valid heuristic keys in helm
  values.yaml comment

### Chores

- Sync uv.lock with pyproject.toml version 0.4.2
  ([`db34015`](https://github.com/teriyakichild/mcp-condenser/commit/db34015e941af94a29d4758513cdf2516d3141c1))

### Documentation

- Add Docker Compose and Helm deployment examples
  ([`1f63415`](https://github.com/teriyakichild/mcp-condenser/commit/1f634152ff3d5083c09af85c68de1ac62b43d38c))

Add examples/ directory with quick-start files for both Docker Compose (single and multi-upstream)
  and Helm (values files and Helmfile). Link to the new examples from the README.

- Improve README accuracy and clarity
  ([`6b1927a`](https://github.com/teriyakichild/mcp-condenser/commit/6b1927ae8a4139591f581d5aed0cf17494f78711))

Fix broken quick start (add -p 9000:9000, note about host.docker.internal on Linux). Rewrite
  subheading and How it works for accuracy: drop "JSON objects" since YAML is also supported,
  replace jargon (elide, homogeneous arrays, numeric tuples) with plain language, explain
  clustered-timestamp condensing. Clarify TOON_FALLBACK description, add transition between Docker
  and source-based usage, restore benchmark summary sentence, and document key config file options
  inline.

- Revamp README and bump chart appVersion to 0.4.2
  ([`4399dff`](https://github.com/teriyakichild/mcp-condenser/commit/4399dffc854fbfd2c3ed0e657cd6c29fa84b93e7))

Rewrite README with a leaner get-started-fast structure: docker run quick start, brief proxy usage
  sections, and env var reference table. Move verbose config examples, header-forwarding docs, and
  per-server tables out of README in favor of links to examples/ and values.yaml. Update Helm chart
  appVersion from 0.2.0 to 0.4.2.

### Features

- Add tunable condensing heuristics
  ([`6f50782`](https://github.com/teriyakichild/mcp-condenser/commit/6f507821dc1e49c976cece84bb37dd31cca036cc))

Make each preprocessing heuristic in preprocess_table() individually toggleable via config, so users
  can disable specific elisions (e.g. timestamp clustering) without switching to toon_only mode.

New Heuristics dataclass with 5 boolean fields (all default true): elide_all_zero, elide_all_null,
  elide_timestamps, elide_constants, group_tuples. Configurable via CONDENSER_HEURISTICS env var or
  per-server "heuristics" dict in the config file. Helm chart updated with the new config value.

### Testing

- Add accuracy benchmark for TOON condensed output
  ([`66912b9`](https://github.com/teriyakichild/mcp-condenser/commit/66912b92aa40f301fee71c9402b9ad883e449b12))

Ollama-based benchmark that verifies an LLM can answer factual questions from condensed TOON output
  vs raw JSON. Includes two fixture sets (toolresult.json, toolresult2_small.json) with 21 total
  questions and configurable model/context settings.


## v0.4.2 (2026-02-20)

### Bug Fixes

- Commit uv.lock for Docker build
  ([`d37c485`](https://github.com/teriyakichild/mcp-condenser/commit/d37c485f96ccd3a49c48804e53693be775c5e3d2))

The Dockerfile copies uv.lock but it was gitignored, causing the Docker build to fail with "not
  found".


## v0.4.1 (2026-02-20)

### Bug Fixes

- Fall back to METRICS_ENABLED/METRICS_PORT env vars in config file mode
  ([`1f65f02`](https://github.com/teriyakichild/mcp-condenser/commit/1f65f02a78ad1bb09dd67e2bc3161f5f246ed1ee))

from_file() ignored the environment variables for metrics settings, so deployments using
  CONDENSER_CONFIG with env-based metrics config (e.g. Helm chart) never actually started the
  metrics server.

### Chores

- Switch release workflow to manual trigger
  ([`228119e`](https://github.com/teriyakichild/mcp-condenser/commit/228119e9d38c8ac3b8daab72088b7e365bd91527))

Replace automatic release on push to master with workflow_dispatch so releases only happen when
  explicitly triggered.

### Continuous Integration

- Add Docker build and push to DockerHub on release
  ([`d249bd7`](https://github.com/teriyakichild/mcp-condenser/commit/d249bd702e692a712cd0b0dead534988067eb4be))


## v0.4.0 (2026-02-20)

### Features

- Add per-upstream headers and header forwarding
  ([`c066862`](https://github.com/teriyakichild/mcp-condenser/commit/c066862421336f939b351e6e9ebedba9edf11dac))

Support per-upstream authentication and header control via two new ServerConfig fields:

- headers: static headers sent to a specific upstream (e.g. bearer tokens) - forward_headers:
  selectively forward and rename incoming client headers per upstream, replacing the default
  forward-everything behavior

Single-upstream mode supports UPSTREAM_MCP_HEADERS env var. Helm chart updated with
  upstreamMcpHeaders value.


## v0.3.1 (2026-02-20)

### Bug Fixes

- Consolidate duplicate helm charts into helm/mcp-condenser
  ([`eb18b9d`](https://github.com/teriyakichild/mcp-condenser/commit/eb18b9d2ae36cba1e1499467f84825241d96d1fd))

Merged chart/ and helm/mcp-condenser/ into a single chart at helm/mcp-condenser/, combining features
  from both: structured config values, health checks, ConfigMap support, pod annotations/labels,
  NOTES.txt, metrics/ServiceMonitor, and generic env passthrough.


## v0.3.0 (2026-02-20)

### Features

- Add prefix_tools option to disable tool name prefixing in multi-upstream mode
  ([`0a31ed8`](https://github.com/teriyakichild/mcp-condenser/commit/0a31ed8096a9d9892ea80e4dcbb455f33f574869))

Adds a global `prefix_tools` config option (default: true) that controls whether tool names are
  prefixed with the server name in multi-upstream mode. When disabled, tools are registered with
  their original names, with collision detection at startup if two servers expose the same tool
  name.


## v0.2.0 (2026-02-20)

### Continuous Integration

- Use RELEASE_TOKEN for semantic release to trigger CI on version commits
  ([`b8c44f9`](https://github.com/teriyakichild/mcp-condenser/commit/b8c44f926becc6c5a8ad20dea763ca39c0c78b1f))

### Features

- Add Prometheus metrics with /metrics endpoint
  ([`322d944`](https://github.com/teriyakichild/mcp-condenser/commit/322d944f84db4f2585c9259f91498c0e6b6b7f58))

Add observability via prometheus-client with counters for requests, tokens, savings, and truncations
  plus histograms for compression ratio and processing duration. Metrics are opt-in via
  METRICS_ENABLED env var and served on a separate HTTP port (default 9090).

- NoopRecorder/PrometheusRecorder behind shared protocol for zero overhead when disabled - Config
  support via env vars and JSON config file - Helm chart with conditional metrics port and
  ServiceMonitor - EXPOSE 9090 in Dockerfile


## v0.1.0 (2026-02-20)

### Bug Fixes

- Group consecutive scalar lines with single newlines in condensed output
  ([`db225a3`](https://github.com/teriyakichild/mcp-condenser/commit/db225a305aa2e43cf58cd3527f45ebf2d2956273))

Top-level scalar key-value pairs were each treated as separate blocks and joined with double
  newlines, creating excessive spacing. Now consecutive scalars are grouped together with single
  newlines, reserving double newlines for section boundaries.

- Rename chart from mcp-condenser-proxy to mcp-condenser
  ([`09c6c56`](https://github.com/teriyakichild/mcp-condenser/commit/09c6c566963b6b14353b78f463d37c6fa74352dc))

- Strip outputSchema and clear structuredContent for condensed tools
  ([`745bc17`](https://github.com/teriyakichild/mcp-condenser/commit/745bc1727f55a05071da3f88e0884bebc9004b29))

The client was displaying the upstream's raw structuredContent (JSON) instead of our condensed text
  content. Fix by stripping outputSchema from tool definitions via on_list_tools so the client
  doesn't expect structuredContent, and clearing it from responses after condensing.

- Update project metadata in pyproject.toml and chart values
  ([`cb18aad`](https://github.com/teriyakichild/mcp-condenser/commit/cb18aad7dfe8e9cbcf8d92e2ed5a0407a99d7f47))

- **ci**: Use empty string for semantic release build_command
  ([`cd52616`](https://github.com/teriyakichild/mcp-condenser/commit/cd526165d301e5e19d321445a46cd51236dd87f5))

### Chores

- Update .gitignore for scratch and data files
  ([`ce527d0`](https://github.com/teriyakichild/mcp-condenser/commit/ce527d0eb7e20c3b516dd7b5e27a00729d534300))

### Continuous Integration

- Add semantic release workflow and fix branch triggers
  ([`aad0ab6`](https://github.com/teriyakichild/mcp-condenser/commit/aad0ab6aba2e8e1f12399affede5dcb87ba613f6))

Add python-semantic-release GitHub Actions workflow to automatically bump versions on merge to
  master. Fix CI triggers from main to master.

### Features

- Add benchmark suite, multi-upstream proxy, and PyPI-ready packaging
  ([`58d5856`](https://github.com/teriyakichild/mcp-condenser/commit/58d5856da44ccc25bfc0d4c30b76afd6cca14d11))

- Benchmark suite with 3 real K8s fixtures validating 57-73% token reduction - Multi-upstream proxy
  via CONDENSER_CONFIG JSON file with per-server tool filtering and condensing settings (backward
  compatible) - Restructure into mcp_condenser/ package with console entry points (mcp-condenser,
  mcp-condenser-proxy) and hatchling build system - Helm chart support for multi-upstream via
  ConfigMap - 84 tests passing

- Add MAX_TOKEN_LIMIT and TOOL_TOKEN_LIMITS for token cap truncation
  ([`5807e43`](https://github.com/teriyakichild/mcp-condenser/commit/5807e43b1319c8035531d397eb21d4f827c63341))

Add global and per-tool token limits as a hard cap safety net applied after condensing. When a tool
  response exceeds its limit, the text is truncated via binary search and a notice is appended.

- Add MIN_TOKEN_THRESHOLD and REVERT_IF_LARGER options
  ([`2e3f71e`](https://github.com/teriyakichild/mcp-condenser/commit/2e3f71e74e4903d32c3151a20e404f420c365253))

Skip the condense pipeline for small responses below a token threshold, and optionally fall back to
  the original response when condensing produces more tokens than the input. Both default to off.

- Add TOON-only tool list and TOON fallback mode
  ([`abd949c`](https://github.com/teriyakichild/mcp-condenser/commit/abd949c7e0216a726835ff6c4d1c54e2b4a41e8e))

Add toon_encode_json() for direct JSON→TOON encoding without semantic preprocessing (no elision of
  constants/zeros/timestamps). Restructure middleware with a 3-tier processing order:
  TOON_ONLY_TOOLS → CONDENSE_TOOLS → TOON_FALLBACK, with stats logging labeled by mode.

- Add YAML input support alongside JSON
  ([`1d5ecc8`](https://github.com/teriyakichild/mcp-condenser/commit/1d5ecc807d9a7d77a873adfed4bbfdd5dfe1fb2b))

YAML tool responses (kubectl, Helm, Ansible) now get parsed and condensed instead of passing through
  unchanged. Adds parse_input() which tries JSON first then falls back to yaml.safe_load, rejecting
  bare scalars and empty input.

- Json condenser with TOON output for LLM context compression
  ([`fe4d381`](https://github.com/teriyakichild/mcp-condenser/commit/fe4d381d6305bc5c4bc2ec3b933516da88d6b458))

Two-layer design: semantic preprocessing (flatten, elide zero/null/constant columns, cluster
  timestamps, collapse numeric tuples, extract nested arrays) followed by TOON serialization for
  compact tabular output.

Achieves ~55% token reduction on Kubelet summary API data (tiktoken measured).

- Mcp proxy layer that condenses JSON tool responses via TOON
  ([`bd92df8`](https://github.com/teriyakichild/mcp-condenser/commit/bd92df8212b0d3888f7fe235c219e9c40a4a3732))

Adds mcp_proxy.py using fastmcp's proxy + middleware to sit between an agent and an upstream MCP
  server, intercepting tool responses and compressing JSON payloads through json_condenser. Non-JSON
  responses pass through unchanged.

### Refactoring

- Rename json_condenser to condenser
  ([`c1fbe04`](https://github.com/teriyakichild/mcp-condenser/commit/c1fbe04ffacffcda4b8e7c9e01bd5c74626ecdf8))

Now that it handles both JSON and YAML, the json_ prefix is misleading.
