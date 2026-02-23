# CHANGELOG


## v0.8.0 (2026-02-23)

### Bug Fixes

- Install project at build time instead of runtime
  ([`4850036`](https://github.com/teriyakichild/mcp-condenser/commit/4850036d7da5ce8114cf27984cb0f7a1c48e3ef1))

Add a second `uv sync --frozen` after copying source to install the project package during the
  Docker build. Replace `uv run` entrypoint with direct .venv/bin invocation so nothing is resolved
  at container start.

- Remove stale QUESTIONS and match functions from accuracy.py
  ([`435e9fe`](https://github.com/teriyakichild/mcp-condenser/commit/435e9fe872b5d969f52e073f57dd3d84b4e2d22e))

The local QUESTIONS dict shadowed the import from fixtures.py, limiting standalone accuracy.py to
  only 2 fixtures instead of all 8. The local match functions also referenced `re` without importing
  it.

- Split accuracy into separate JSON/TOON tables, remove raw backup
  ([`dbe7119`](https://github.com/teriyakichild/mcp-condenser/commit/dbe7119203125e283283304a02475c2f63df1da6))

Split the combined accuracy matrix into separate JSON (baseline) and TOON (balanced profile) tables
  for readability. Remove raw_results_pre_profiles.json from repo.

### Documentation

- Add CSV/XML to README, note on CSV token behavior
  ([`b1305fe`](https://github.com/teriyakichild/mcp-condenser/commit/b1305fe23340f007a81e4009ea31b304ea623f98))

Update supported formats, CLI examples, benchmark table, and question count. Add note explaining
  that CSV already being tabular means TOON adds minimal overhead — the value is auto-detection,
  type inference, and heuristic column elision rather than token reduction.

- Rename JSON to Raw in README benchmark tables
  ([`4d4aaa6`](https://github.com/teriyakichild/mcp-condenser/commit/4d4aaa6dfa335581705f928e9df7edec331169cd))

### Features

- Add app_performance.csv benchmark fixture
  ([`ff03d7d`](https://github.com/teriyakichild/mcp-condenser/commit/ff03d7df752c8e2dad9cffff444bb47e18527750))

30 microservices x 25 columns APM dashboard export designed to exercise TOON heuristics: 4 all-zero
  cols, 3 all-null cols, 1 constant col elided; latency and errors tuple-grouped (25→13 effective
  columns). 15 accuracy questions including annotation-reading tests. qwen3:4b scores 93% TOON vs
  87% raw at 1.6x speed.

- Add CSV and XML benchmark fixtures with accuracy questions
  ([`de3770a`](https://github.com/teriyakichild/mcp-condenser/commit/de3770a6d470f8abf17fe68134d69b854c4dee67))

Add server_metrics.csv (25 servers x 10 columns) and deploy_inventory.xml (20 deployments across 3
  environments) as accuracy benchmark fixtures. Update load_sample to handle non-JSON formats via
  parse_input, add 15 questions each covering direct lookups, filtering, cross-reference, and
  multi-hop queries.

XML fixture shows 65.6% token reduction from eliminating duplicated tags — exactly the enterprise
  API use case the condenser targets.

- Add CSV/TSV parser with type inference
  ([`a35492c`](https://github.com/teriyakichild/mcp-condenser/commit/a35492c8d9e1c3d8df476fa91c545c443a79f9c1))

Register a new CSV parser after JSON/YAML in the parser registry. Uses csv.Sniffer for dialect
  detection (comma, tab, pipe, semicolon), requires 2+ columns and at least one data row. Type
  normalization converts numeric strings to int/float and empty values to None.

- Add format_hint config for per-tool format override
  ([`1d8dea4`](https://github.com/teriyakichild/mcp-condenser/commit/1d8dea4c413406f159a2b37cab13ad44d3e4ef1e))

ServerConfig gains format_hint and tool_format_hints fields, parsed from FORMAT_HINT /
  TOOL_FORMAT_HINTS env vars and JSON config. The proxy passes the resolved hint through to
  parse_input().

- Add XML parser with tree-to-dict conversion
  ([`17ca4db`](https://github.com/teriyakichild/mcp-condenser/commit/17ca4dbe21c3f8dcfd6e248f314634ccfada1b89))

Uses xml.etree.ElementTree to parse XML into nested dicts/lists that the existing condense pipeline
  handles natively. Attributes become @attr keys, repeated child elements become lists, and text
  values get int/float/bool coercion. Registered after CSV (lowest auto-detect priority).

### Refactoring

- Extract parser registry into parsers.py
  ([`8ba88e5`](https://github.com/teriyakichild/mcp-condenser/commit/8ba88e5b1b778f5cd92ac84a4756cb5c7bda8d8e))

Move parse_input() from condenser.py into a new parsers module with an extensible registry (Parser
  NamedTuple, PARSER_REGISTRY, register_parser). Existing importers continue to work via re-export
  from condenser.py.

- Rename benchmark format label from json to raw
  ([`ad6057f`](https://github.com/teriyakichild/mcp-condenser/commit/ad6057f038c61e2552a200446abe08a979a80518))

The baseline format is the original input (JSON, CSV, XML, etc.), not always JSON. Rename format
  field, display labels, variable names, and help text throughout accuracy.py and matrix.py. Also
  add app_performance.csv to matrix DEFAULT_FIXTURES.

- Rename condense_json/toon_encode_json to format-agnostic names
  ([`7d24b54`](https://github.com/teriyakichild/mcp-condenser/commit/7d24b54b50944478ccba71a4ccd30ed4342520e3))

condense_json() → condense_text(), toon_encode_json() → toon_encode(). Old names remain as
  deprecated aliases that emit DeprecationWarning. All internal callers updated to use new names.


## v0.7.0 (2026-02-23)

### Bug Fixes

- Update GitHub URLs from logdna to teriyakichild
  ([`4613815`](https://github.com/teriyakichild/mcp-condenser/commit/46138158abac759e461ae42cf10cee2e3729004b))

### Documentation

- Add shields.io badges to README
  ([`8890266`](https://github.com/teriyakichild/mcp-condenser/commit/8890266a0ec09c776a35b2ae354c8feffd35bdb5))

- Update benchmark reports with balanced profile results
  ([`ef06aa7`](https://github.com/teriyakichild/mcp-condenser/commit/ef06aa73aef3f2a6ac8dcd9679080d6935d65569))

Rerun full accuracy matrix (5 models × 4 fixtures) using the balanced profile with TOON-only mode.
  EC2 accuracy improved from 0% to 80-100% on qwen3 models thanks to wide_table_format=split.

### Features

- Add --profile and --toon-only flags to benchmark matrix
  ([`c72ad7c`](https://github.com/teriyakichild/mcp-condenser/commit/c72ad7c03051c57ee63bf2c70fee1dd1f52ce76e))

Support heuristics profiles and TOON-only mode in the matrix runner, passing resolved heuristics
  through to token/context table generation. Back up pre-profile raw results for historical
  comparison.

- Add heuristics profiles (balanced, compact, precise)
  ([`8eb8ba0`](https://github.com/teriyakichild/mcp-condenser/commit/8eb8ba01b85575d818b74d2024d26ca1e8f52b08))

Named profiles provide preset heuristic configurations selectable via config, env var
  (CONDENSER_PROFILE), or benchmark CLI (--profile). Resolution order: profile defaults → server
  heuristics → tool_heuristics.

- Add wide table rendering and per-tool heuristics
  ([`05ff812`](https://github.com/teriyakichild/mcp-condenser/commit/05ff812678e93720355926a0ffa13ab153b3a819))

Resolve merge conflicts from feat/wide-table-rendering branch. Adds two alternative renderers for
  tables that exceed a column threshold:

- vertical: key-value blocks per row, labeled by identity column - split: multiple narrow sub-tables
  grouped by column prefix, with identity columns repeated in each

New heuristics: wide_table_threshold (column count trigger), wide_table_format ("vertical" or
  "split"). Per-tool heuristic overrides via tool_heuristics config. Expanded benchmark questions
  for K8s fixtures.


## v0.6.0 (2026-02-23)

### Features

- Add live progress output to accuracy benchmark
  ([`17c854d`](https://github.com/teriyakichild/mcp-condenser/commit/17c854d02c5687ef4dc691f529aa010c37cece5f))

Print per-question status lines to stderr as the benchmark runs, showing pass/fail/skip, format,
  fixture, question, and elapsed time.

- Add max_table_columns and elide_mostly_zero_pct heuristics for wide table readability
  ([`21ad4bd`](https://github.com/teriyakichild/mcp-condenser/commit/21ad4bd7f670b5e985ff11a17eb1372ba2c288c6))

Add two new experimental heuristics to help small LLMs parse wide tables: - max_table_columns: caps
  table width, dropping rightmost columns (identity columns survive via ordering) -
  elide_mostly_zero_pct: removes columns where most values are zero, annotating outliers with
  identity labels

Also adds --heuristics flag to benchmarks/accuracy.py for testing strategies without code changes,
  and updates config.py to support float-valued heuristic parameters.

- Add multi-hop, arithmetic, and ranking benchmark questions
  ([`eb47680`](https://github.com/teriyakichild/mcp-condenser/commit/eb47680aea79c05e5980f0dbb49f9aaa0c430f84))

Add 12 harder questions requiring multi-step reasoning: multi-hop lookups, percentage calculations,
  inverse filtering, ranking beyond top-1, cross-section joins, and reading elided annotation
  values.

- Add per-tool heuristic overrides and harder benchmark questions
  ([`880e371`](https://github.com/teriyakichild/mcp-condenser/commit/880e371096c41dc6eae6a0afee85ff8c8efc415a))

- tool_heuristics config allows per-tool heuristic overrides that merge on top of base server
  heuristics - fix string value parsing in CONDENSER_HEURISTICS env var (previously coerced non-bool
  strings to True) - add 12 harder cross-reference/comparison/aggregation benchmark questions

- Expand benchmark suite with multi-model matrix and new fixtures
  ([`cda4274`](https://github.com/teriyakichild/mcp-condenser/commit/cda4274df9ff68a7be9188da75321176f6f8b0cf))

Add multi-model accuracy benchmark infrastructure: - benchmarks/fixtures.py: shared questions (90
  across 5 fixtures), match functions, and fixture metadata extracted from accuracy.py -
  benchmarks/matrix.py: multi-model orchestrator with resume support, incremental saves, and
  markdown report generation - benchmarks/accuracy.py: refactored to import from fixtures.py, added
  per-question error handling and 600s timeout

Add synthetic test fixtures: - tests/fixtures/aws_ec2_instances.json: 20 EC2 instances (33K tokens,
  87% reduction) with deterministic generator script - tests/fixtures/db_query_results.json: 150 SQL
  order rows (26K tokens, 57% reduction) with deterministic generator script

Benchmark results across 5 models (qwen3:1.7b/4b, llama3.1:8b, qwen3:14b/30b) show TOON matches or
  beats JSON accuracy on Kubernetes fixtures (100% TOON on both K8s fixtures for all models 4b+)
  while achieving 57-87% token reduction.

Document EC2 Tags condensing gap in docs/ec2-tags-fix.md — nested tag arrays are silently dropped
  during sub-table rendering, making 5 of 15 EC2 questions impossible to answer from TOON output.

- Pivot Key-Value arrays (AWS Tags) into scalar columns
  ([`e0c14fd`](https://github.com/teriyakichild/mcp-condenser/commit/e0c14fd1307e8a24e97e134eb1f4df437d6ab5b5))

Detect [{Key, Value}] arrays (AWS tag convention) and pivot them into scalar columns on the parent
  row (e.g. Tags.Name, Tags.Environment) instead of extracting them as cross-referenced sub-tables.

### Refactoring

- Split benchmark reports into separate JSON and TOON tables
  ([`eb0cbc4`](https://github.com/teriyakichild/mcp-condenser/commit/eb0cbc4c71fc08ce958ca75fe0cdadde12a394ad))

The combined JSON/TOON accuracy cells were hard to scan. Split into two independent tables and move
  context window enablement under a "Local Models" heading since frontier models don't have those
  limits.


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
