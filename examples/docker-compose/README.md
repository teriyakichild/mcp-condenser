# Docker Compose Quick Start

## Single upstream

Proxy a single MCP server and condense all tool responses:

```bash
docker compose up
```

Edit `docker-compose.yml` to set `UPSTREAM_MCP_URL` to your MCP server.

## Multi-upstream

Aggregate multiple MCP servers behind one endpoint:

```bash
docker compose -f docker-compose.multi.yml up
```

Edit `config.json` to configure your upstream servers.

## Connecting

Point your MCP client (Claude Desktop, Claude Code, etc.) at:

```
http://localhost:9000/mcp
```
