FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project

COPY README.md ./
COPY mcp_condenser/ mcp_condenser/

ENV PROXY_HOST=0.0.0.0
ENV PROXY_PORT=9000
EXPOSE 9000

ENTRYPOINT ["uv", "run", "mcp-condenser-proxy"]
