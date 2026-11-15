# Using Luiccian QGIS MCP with Agent Clients

Luiccian QGIS MCP uses the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) over **stdio**
transport, so it integrates directly with **Antigravity**, **Claude Code**, **Claude Desktop**, and
any other MCP-compatible client configured via manual JSON.

## How it works

```
Agent (LLM) ←→ MCP Client ←→ stdio ←→ luiccian-qgis-mcp ←→ TCP socket ←→ QGIS Plugin
```

The MCP server is a standalone Python process launched by your client. Any agent that can spawn an
MCP stdio server (or connect over Streamable HTTP) and call tools can drive QGIS.

---

## Prerequisites

1. **QGIS 3.28+ (3.x or 4.x)** with the **Luiccian QGIS Listener** plugin installed:
   - **Download or build the ZIP:** Download `qgis_listener_v<version>.zip` from the
     [releases page](https://github.com/LuiccianDev/qgis-mcp/releases), or build it locally from a
     checkout with:
     ```bash
     uv run --no-sync python scripts/build_plugin_zip.py
     # Creates: dist/qgis_listener_v<version>.zip
     ```
   - **Install only the plugin in QGIS:**
     - **QGIS GUI:** `Plugins` › `Manage and Install Plugins` › **Install from ZIP** and select the `.zip` file.
     - **Terminal (plugin-only):** run `python install.py --list-qgis` to inspect QGIS profiles, then
       `python install.py --plugin-only --from-zip` (or `--from-zip dist/qgis_listener_v<version>.zip`).
   - Restart QGIS if prompted, then open the Luiccian QGIS Listener dock widget and click **Start Server**
     (listens on `localhost:9878` by default).

2. **[uv](https://docs.astral.sh/uv/getting-started/installation/)** - the Python package
   runner used to launch the MCP server without a manual `pip install`.

---

## MCP client configuration

Any MCP-capable client that accepts the standard `mcpServers` JSON schema can use either of these blocks:

**Remote (no local clone needed):**
```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": [
        "--from",
        "https://github.com/LuiccianDev/qgis-mcp/archive/refs/heads/master.zip",
        "luiccian-qgis-mcp"
      ]
    }
  }
}
```

**Local repository checkout:**
```json
{
  "mcpServers": {
    "qgis": {
      "command": "uv",
      "args": ["--directory", "/path/to/qgis-mcp", "run", "--no-sync", "src/qgis_mcp/server.py"]
    }
  }
}
```

Or generate this snippet from the terminal with `python install.py --print-config` (add `--remote` for the `uvx` variant).

### With optional environment variables

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": [
        "--from",
        "https://github.com/LuiccianDev/qgis-mcp/archive/refs/heads/master.zip",
        "luiccian-qgis-mcp"
      ],
      "env": {
        "QGIS_MCP_HOST": "localhost",
        "QGIS_MCP_PORT": "9878",
        "QGIS_MCP_TOKEN": "your-long-random-secret"
      }
    }
  }
}
```

`QGIS_MCP_TOKEN` is optional: the server reads the shared token file before
falling back to "no authentication", so a client that does not set it still
authenticates with the token the plugin's Configurator generated. See
[The shared token file](#the-shared-token-file) below.

---

## Supported clients & config locations

`python install.py --non-interactive --clients <name>` configures these automatically (merging into existing JSON files and leaving a `.bak` backup beside them):

| Client | `--clients` name | Config file / CLI | Root key |
|---|---|---|---|
| Antigravity | `antigravity` | `~/.gemini/antigravity/mcp_config.json` (`$ANTIGRAVITY_CONFIG_DIR/mcp_config.json`) | `mcpServers` |
| Claude Desktop | `claude-desktop` | `%APPDATA%\Claude\claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Linux: `~/.config/Claude/`) | `mcpServers` |
| Claude Code | `claude-code` | `claude mcp add -s user qgis -- ...` | `~/.claude.json` |
| Manual JSON | `manual` | Prints JSON snippet (`python install.py --print-config`) | `mcpServers` |

You can also view or apply these configurations inside QGIS from `Plugins` › `Luiccian QGIS Listener` › **MCP Setup Configurator**.

### Verification steps

1. Start your client (Antigravity or Claude) after updating the MCP configuration.
2. Ask the agent to list tools or verify the connection:
   ```
   Call the QGIS ping tool to verify the connection.
   ```
3. With QGIS open and **Luiccian QGIS Listener** running, `ping` returns `{"pong": true}` and all 128 tools (or 27 in compound mode) are available.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QGIS_MCP_HOST` | `localhost` | Host where the QGIS plugin socket listens |
| `QGIS_MCP_PORT` | `9878` | Port for the QGIS plugin socket |
| `QGIS_MCP_INSTANCES` | _(unset)_ | Address several QGIS windows from one server: `name=port` or `name=host:port`, comma-separated (e.g. `default=9878,b=9879`). Unset = one instance named `default` from `QGIS_MCP_HOST`/`QGIS_MCP_PORT`. See [Multiple QGIS instances](#multiple-qgis-instances). |
| `QGIS_MCP_TOKEN` | _(unset)_ | Optional shared secret; overrides the token file when set. See [The shared token file](#the-shared-token-file). |
| `QGIS_MCP_TRANSPORT` | `stdio` | MCP transport: `stdio` or `streamable-http` |
| `QGIS_MCP_LOG_FILE` | `~/.local/share/qgis-mcp/server.log` | Log file path (empty to disable) |
| `QGIS_MCP_LOG_LEVEL` | `INFO` | File log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `QGIS_MCP_TOOL_MODE` | `granular` | `granular` (128 tools) or `compound` (27 grouped tools) |

---

## The shared token file

The plugin and the MCP server both read the same per-user token file, so a token is
generated once and never copied between two configs:

| OS | Token file |
|----|------------|
| Windows | `%APPDATA%\qgis-mcp\token` |
| Linux / macOS | `$XDG_CONFIG_HOME/qgis-mcp/token` (default `~/.config/qgis-mcp/token`) |

Resolution order is `QGIS_MCP_TOKEN`, then the file, then no authentication. The
plugin's **Setup & Configurator** has a **Security** group that generates, copies,
rotates and revokes the token; it is the only writer. Both halves read the file on
every command, so a rotation takes effect on the next call without restarting QGIS
or the agent.

If `QGIS_MCP_TOKEN` is set in the environment QGIS runs in, it wins over the file
and the Configurator disables the generate/revoke buttons. Set the same value in the
client's `env` block to keep the secret out of the file entirely.

---

## Multiple QGIS instances

One MCP server registration can drive several running QGIS windows - no need to register
the server once per port.  Start each QGIS with the plugin on its own port, then list them
in `QGIS_MCP_INSTANCES`:

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": [
        "--from",
        "https://github.com/LuiccianDev/qgis-mcp/archive/refs/heads/master.zip",
        "luiccian-qgis-mcp"
      ],
      "env": {
        "QGIS_MCP_INSTANCES": "default=9878,planning=9879,archive=lab-box:9880"
      }
    }
  }
}
```

- Every tool takes an optional `instance` argument: `get_layers(instance="planning")`.
- `list_qgis_instances` reports the configured names, host, port, and whether each is
  currently reachable.
- An unknown name is rejected with the list of configured names.
- Instance names match `[A-Za-z0-9_-]+`.  Entries without a host use `QGIS_MCP_HOST`
  (default `localhost`).
- Each instance keeps its own pooled socket and its own lock, so two instances can be
  driven concurrently without blocking each other.
- Omitting `instance` targets the entry named `default`; when no entry is called `default`,
  the **first** entry listed is used, so `planning=9877,archive=9878` works without
  renaming anything.
- **Not supported with `QGIS_MCP_TOOL_MODE=compound`.**  Compound tools carry no `instance`
  argument, so configuring more than one instance in compound mode refuses to start rather
  than silently routing every call to one QGIS.
- `QGIS_MCP_TOKEN` is shared by all instances - set the same secret in each QGIS.

---

## Troubleshooting

### "No response from QGIS" / connection refused

- Confirm QGIS is open and the Luiccian QGIS Listener dock widget shows **Server running**.
- Check the port: the plugin defaults to `9878`.  Override with `QGIS_MCP_PORT` if you
  changed it in the plugin settings.
- On macOS/Linux run `ss -tlnp | grep 9878` (or `netstat -an | grep 9878`) to confirm the
  port is listening.

### Tools not appearing / empty tool list

- Make sure the MCP server process started successfully.  Run it manually to check:
  ```bash
  uvx --from https://github.com/LuiccianDev/qgis-mcp/archive/refs/heads/master.zip luiccian-qgis-mcp
  ```
  It should print nothing and wait (reading MCP messages from stdin). `Ctrl-C` to quit.
- If you see `ModuleNotFoundError`, `uv`/`uvx` is not installed or not on `PATH`.
- If you see `Connection refused`, the QGIS plugin is not listening yet - start it first.

### Agent says "tool call failed" for every command

- The MCP server started but can't reach QGIS.  Confirm the plugin is running (see above).
- If authentication is on, the client must present the current token: it reads the shared
  file automatically, so a rotation needs no client change. Only if you overrode it with
  `QGIS_MCP_TOKEN` must the client's `env` block carry the **same** value.

### Streamable-HTTP transport (remote / multi-client)

If the agent cannot spawn subprocesses but can make HTTP requests, set
`QGIS_MCP_TRANSPORT=streamable-http` in the server environment and point the client at
`http://localhost:8000/mcp/` (default FastMCP HTTP endpoint).

---

## Compound tool mode

If your agent has a limited context window or struggles with 128 separate tool schemas,
enable compound tool mode to reduce the tool count to 27 grouped tools (no loss of
functionality - every granular command is reachable through an action):

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": ["--from", "...", "luiccian-qgis-mcp"],
      "env": { "QGIS_MCP_TOOL_MODE": "compound" }
    }
  }
}
```

Each compound tool takes two arguments: `action` (string, required) selects the operation,
and `params` (object, optional) carries that action's parameters.  Parameters are **not**
top-level tool arguments - they always go inside `params`:

```json
{
  "name": "project",
  "arguments": { "action": "load", "params": { "path": "/data/city.qgz" } }
}
```

```json
{
  "name": "expression",
  "arguments": { "action": "evaluate", "params": { "expression": "2 + 3" } }
}
```

Omit `params` entirely for actions that take none (`{"action": "ping"}`).  Each tool's
description lists the accepted keys per action.

The groups are:
`system`, `project`, `layer`, `features`, `selection`, `style`, `canvas`, `render`, `processing`, `code`, `batch`, `layer_tree`, `plugins`, `variables`, `settings`, `expression`, `query`, `transform`, `message_log`, `layer_property`, `field`, `analysis`, `bookmarks`, `map_themes`, `active_layer`.

---

## Complete workflow examples

These examples show end-to-end workflows you can paste directly into your agent.

### Example 1: Create a styled map from scratch

This workflow creates a new project, loads data, applies styling, and exports a layout.

```
I need to create a map showing land use zones. Please:

1. Create a new QGIS project and set the CRS to EPSG:4326.
2. Load the vector layer "/data/landuse.gpkg" layer "zones".
3. Apply a categorized style using the "category" field with distinct colors.
4. Add labels showing the "name" attribute with 10pt bold text.
5. Create a print layout called "LandUse_Map" with:
   - A map item showing the styled layer
   - A title label "Land Use Zoning Map"
   - A legend
   - A scalebar
   - A north arrow
6. Export the layout as PDF to "/output/landuse_map.pdf".
7. Save the project to "/output/landuse_project.qgz".
```

### Example 2: Batch processing with background jobs

For long-running algorithms, use background jobs to keep QGIS responsive.

```
I have a large rivers layer that needs buffering. Please:

1. Start a background processing job to buffer the "rivers" layer by 100 meters
   using the native:buffer algorithm.
2. While the job runs, list the current processing job status.
3. Poll the job status every few seconds until it completes.
4. Once done, add the buffered result layer to the project.
5. Apply a semi-transparent blue style to the buffered zones.
```

### Example 3: Feature editing with validation

Edit features safely using edit sessions with rollback support.

```
I need to update parcel attributes. Please:

1. List all features in the "parcels" layer where "status" = "pending".
2. Start editing the "parcels" layer.
3. For each pending parcel, update the "status" field to "reviewed" and
   set "review_date" to today's date.
4. Commit the edits.
5. Verify the changes by counting features with "status" = "reviewed".
6. If anything goes wrong, rollback the edits.
```

### Example 4: Multi-instance workflow

Control multiple QGIS windows from one agent session.

```
I have two QGIS instances configured: "planning" and "archive".

1. List the configured QGIS instances and their status.
2. On the "planning" instance:
   - Load the project "/data/planning_current.qgz"
   - Add a new memory layer for draft features
3. On the "archive" instance:
   - List all layers in the current project
   - Export the project to "/archive/planning_2024.qgz"
4. Compare the layer counts between both instances.
```

### Example 5: Data analysis with SQL and expressions

Query and analyze data across layers.

```
I need to analyze parcel ownership patterns. Please:

1. Execute SQL to join parcels and owners:
   SELECT p.id, p.area, o.name, o.type
   FROM parcels p
   JOIN owners o ON p.owner_id = o.id
   WHERE p.area > 1000
2. Get field statistics for the "area" field in the "parcels" layer.
3. Get unique values for the "owner_type" field.
4. Evaluate the expression "area * price_per_sqm" on the "parcels" layer.
5. Create a graduated style based on the calculated value.
```

### Example 6: Coordinate transformation

Transform coordinates between CRS systems.

```
I have coordinates in WGS84 that need to be transformed to UTM zone 33N.

1. Transform the following points from EPSG:4326 to EPSG:25833:
   - Point 1: 8.5, 47.4
   - Point 2: 8.6, 47.5
2. Also transform this bounding box: [8.4, 47.3, 8.7, 47.6]
3. Create a memory layer with the transformed coordinates.
```

### Example 7: Checkpoint and session management

Save and restore project state safely.

```
Before making changes, I want to save a checkpoint.

1. Create a checkpoint of the current project state.
2. Make some changes: add a layer, modify styling, edit features.
3. Export the session as a script for reproducibility.
4. If the changes are not what I wanted, restore the checkpoint.
5. List available checkpoints and their details.
```

### Example 8: Database connection and layer import

Work with PostgreSQL databases.

```
I need to connect to a PostgreSQL database and import layers.

1. List available database connections.
2. Create a new PostgreSQL connection named "city_data" with:
   - Host: localhost
   - Port: 5432
   - Database: city_gis
   - Using authentication manager config "city_auth"
3. List the tables available in the "city_data" connection.
4. Add the "streets" table as a layer to the project.
5. Import the "buildings" layer from the current project into the database.
```

---

## Agent Skills (`skills/`)

The repository ships two ready-to-use Agent Skills under `skills/` for AI coding/agent clients that support `SKILL.md`:

- [`skills/qgis-mcp-tools/SKILL.md`](../skills/qgis-mcp-tools/SKILL.md) (with [`references/tool-catalog.md`](../skills/qgis-mcp-tools/references/tool-catalog.md)) — Reference for all 128 granular tools, 27 compound tools (`QGIS_MCP_TOOL_MODE=compound`), `instance=` routing, feature pagination (`limit <= 50`), timeouts, edit buffering, `batch_commands` restrictions, and `qgis://*` resources.
- [`skills/qgis-mcp-workflows/SKILL.md`](../skills/qgis-mcp-workflows/SKILL.md) — Recommended call chains (preflight, safe exploration, checkpoints + edit sessions, CRS-safe processing, styling + layout export, database connections) and anti-patterns to avoid.

To make them available in an Agent Skills-compatible client, point your client's skills directory at `skills/` or copy/symlink `skills/qgis-mcp-tools` and `skills/qgis-mcp-workflows` into your local skills folder.
