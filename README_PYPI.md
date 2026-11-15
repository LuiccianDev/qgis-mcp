# Luiccian QGIS MCP (`luiccian-qgis-mcp`)

Model Context Protocol (MCP) server for controlling [QGIS](https://qgis.org/) (3.28–4.x) from AI coding agents (**Antigravity**, **Claude Code**, **Claude Desktop**, and any MCP-compatible client).

> **Note — Two separate components:**
> This PyPI package (`luiccian-qgis-mcp`, **Apache-2.0**) provides **only the MCP server** (`src/qgis_mcp`).
> To connect to QGIS, you also need the companion **Luiccian QGIS Listener** plugin (`qgis_listener`, **GPL-2.0-or-later**) installed inside QGIS. Download `qgis_listener_v<version>.zip` from [GitHub Releases](https://github.com/LuiccianDev/qgis-mcp/releases) and install it via **Plugins → Manage and Install Plugins → Install from ZIP**.

## Architecture

```text
AI Agent  <--MCP (stdio / HTTP)-->  luiccian-qgis-mcp (PyPI)  <--TCP :9878-->  QGIS Listener Plugin
```

## Quick Start

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/getting-started/installation/).

Run directly without installing globally:

```bash
uvx luiccian-qgis-mcp
```

Or install into an environment:

```bash
pip install luiccian-qgis-mcp
luiccian-qgis-mcp
```

### MCP Client Configuration

Add the following to your MCP client configuration (e.g., `~/.gemini/antigravity/mcp_config.json`, Claude Desktop, or `.mcp.json`):

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": ["luiccian-qgis-mcp"]
    }
  }
}
```

For **Claude Code**:

```bash
claude mcp add -s user qgis -- uvx luiccian-qgis-mcp
```

## Capabilities

128 MCP tools (or 27 grouped tools with `QGIS_MCP_TOOL_MODE=compound`) covering:

- **Project & Session:** info, load/save, checkpoints, session replay export
- **Layers & Tree:** vector, raster, web/XYZ/WMS, memory layers, joins, groups, ordering
- **Features & Editing:** query, spatial/attribute selection, add/update/delete, buffered edit sessions, undo/redo
- **Processing & Raster:** run algorithms, background jobs, raster calculator, zonal statistics, spatial joins
- **Styling & Layouts:** symbology, QML styles, print layouts, legends, scalebars, atlas export, map & 3D rendering
- **Database Connections & Python:** saved PostgreSQL/GeoPackage/SpatiaLite connections, cross-layer SQL, `execute_code`

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `QGIS_MCP_HOST` | `localhost` | Host where the QGIS Listener plugin is running |
| `QGIS_MCP_PORT` | `9878` | TCP port of the QGIS Listener plugin |
| `QGIS_MCP_INSTANCES` | _(unset)_ | Comma-separated `name=port` / `name=host:port` list for multiple QGIS windows |
| `QGIS_MCP_TOKEN` | _(unset)_ | Shared auth token (overrides the token file written by the QGIS plugin) |
| `QGIS_MCP_TOOL_MODE` | `granular` | `granular` (128 tools) or `compound` (27 grouped tools) |
| `QGIS_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |

## Links

- **Source & Full Documentation:** https://github.com/LuiccianDev/qgis-mcp
- **QGIS Plugin Releases:** https://github.com/LuiccianDev/qgis-mcp/releases
- **Issues:** https://github.com/LuiccianDev/qgis-mcp/issues
