<div align="center">

# Luiccian QGIS MCP

[![PyPI](https://img.shields.io/pypi/v/luiccian-qgis-mcp?color=blue)](https://pypi.org/project/luiccian-qgis-mcp/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![QGIS](https://img.shields.io/badge/QGIS-3.28%E2%80%934.x-green)](https://qgis.org/)
[![Tests](https://github.com/LuiccianDev/qgis-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/LuiccianDev/qgis-mcp/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0%20%2F%20GPL--2.0--or--later-lightgrey)](LICENSE)

Connect [QGIS](https://qgis.org/) to any AI agent that speaks the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), so the agent drives QGIS directly: manage layers, edit features, run processing algorithms, render maps, author print layouts, and execute cross-layer SQL.

</div>

---

## Architecture

```text
AI Agent  ←→  MCP Server (FastMCP)  ←→  TCP Socket  ←→  QGIS Plugin (QTimer)  ←→  PyQGIS API
```

1. **QGIS Plugin** (`qgis_listener/`, **GPL-2.0-or-later**) — Runs inside QGIS as a non-blocking TCP socket server (`QTimer` loop) processing JSON commands on the main thread.
2. **MCP Server** (`src/qgis_mcp/`, **Apache-2.0**) — Standalone Python process exposing QGIS operations via [FastMCP](https://gofastmcp.com/) (installable via [`luiccian-qgis-mcp`](https://pypi.org/project/luiccian-qgis-mcp/) on PyPI or from source).

---

## Installation

Requires **QGIS 3.28+**, **Python 3.12+**, and **[uv](https://docs.astral.sh/uv/getting-started/installation/)**.

### 1. Install the QGIS plugin (`qgis_listener`)

You can install **only the QGIS plugin** without cloning the repository or altering MCP client configs:

#### A. Download or build the plugin ZIP

- **From GitHub Releases (recommended):** Download the latest `qgis_listener_v<version>.zip` from the [Releases page](https://github.com/LuiccianDev/qgis-mcp/releases).
- **Build locally from source:**
  ```bash
  uv run --no-sync python scripts/build_plugin_zip.py
  # Creates: dist/qgis_listener_v0-1-1.zip
  ```

#### B. Install the plugin in QGIS

- **From QGIS (GUI):** Open `Plugins` > `Manage and Install Plugins` > **Install from ZIP**, select `qgis_listener_v<version>.zip`, enable **Luiccian QGIS Listener**, restart QGIS if prompted, and click **Start Server** in the Luiccian QGIS Listener dock widget.
- **From the terminal (`install.py`, plugin-only):**
  ```bash
  # Check detected QGIS 3 / QGIS 4 installations and user profiles
  python install.py --list-qgis

  # Download/build the ZIP and extract only the plugin into QGIS
  python install.py --plugin-only --from-zip

  # Or install a specific ZIP archive into a specific QGIS profile
  python install.py --plugin-only --from-zip dist/qgis_listener_v0-1-1.zip --profile default
  ```

### 2. Connect your AI agent (Antigravity / Claude / Manual)

With `luiccian-qgis-mcp` published on PyPI, `uvx luiccian-qgis-mcp` runs the MCP server with zero manual setup.

- **PyPI (recommended):** `"command": "uvx", "args": ["luiccian-qgis-mcp"]`
- **From GitHub `master` (bleeding edge):** `uvx --from https://github.com/LuiccianDev/qgis-mcp/archive/refs/heads/master.zip luiccian-qgis-mcp`
- **From local checkout:** `uv --directory "/path/to/qgis-mcp" run --no-sync src/qgis_mcp/server.py` (or `python install.py` without `--remote`)

<details open>
<summary>Antigravity (<code>antigravity</code>)</summary>

Config file: `~/.gemini/antigravity/mcp_config.json` (`%USERPROFILE%\.gemini\antigravity\mcp_config.json` on Windows, or override via `ANTIGRAVITY_CONFIG_DIR`).

**Manual JSON (`mcp_config.json`, PyPI):**
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

**Automatic setup via `install.py`:**
```bash
# Remote mode (uvx from GitHub)
python install.py --non-interactive --clients antigravity --remote

# Or local repository checkout
python install.py --non-interactive --clients antigravity
```

**Manual JSON (`mcp_config.json`, local checkout):**
```json
{
  "mcpServers": {
    "qgis": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/qgis-mcp",
        "run",
        "--no-sync",
        "src/qgis_mcp/server.py"
      ]
    }
  }
}
```

</details>

<details>
<summary>Claude Code (<code>claude-code</code>)</summary>

**Via Claude CLI (PyPI, recommended):**
```bash
claude mcp add -s user qgis -- uvx luiccian-qgis-mcp
```

**Automatic setup via `install.py`:**
```bash
python install.py --non-interactive --clients claude-code --remote
```

**Local checkout mode:**
```bash
claude mcp add -s user qgis -- uv --directory "/path/to/qgis-mcp" run --no-sync src/qgis_mcp/server.py
```

Scope reference:

| Flag | Stored in | Visible to |
|------|-----------|-----------|
| `-s local` (default) | local user project state / `.mcp.json` | You, this project |
| `-s project` | `.mcp.json` (committed) | Whole team, this project |
| `-s user` | `~/.claude.json` | You, every project |

</details>

<details>
<summary>Claude Desktop (<code>claude-desktop</code>)</summary>

Config file:
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

**Manual JSON (`claude_desktop_config.json`, PyPI):**
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

**Automatic setup via `install.py`:**
```bash
python install.py --non-interactive --clients claude-desktop --remote
```

**Manual JSON (`claude_desktop_config.json`, local checkout):**
```json
{
  "mcpServers": {
    "qgis": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/qgis-mcp",
        "run",
        "--no-sync",
        "src/qgis_mcp/server.py"
      ]
    }
  }
}
```

</details>

<details>
<summary>Manual JSON (<code>manual</code> — any other MCP client)</summary>

Generate the exact JSON snippet for your environment:
```bash
python install.py --print-config           # local checkout
python install.py --print-config --remote  # uvx from GitHub
```

Or paste this into your client's MCP configuration file (PyPI):
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

You can also open `Plugins` > `Luiccian QGIS Listener` > **MCP Setup Configurator** inside QGIS to copy or apply the configuration for `antigravity`, `claude-code`, `claude-desktop`, or `manual`.

</details>

For a full setup guide, troubleshooting steps, and compound-tool mode configuration see [`docs/agent-integration.md`](docs/agent-integration.md).

---

## Usage

1. **Start the plugin** — In QGIS, click the **Luiccian QGIS Listener** toolbar button (or `Plugins` > `Luiccian QGIS Listener`) and click **Start Server**.
2. **Talk to your agent** — The MCP tools appear automatically. Ask the agent to work with your QGIS project.

### Example prompts

#### Basic workflow

```text
You have access to QGIS tools. Do the following:
1. Ping to check the connection
2. Create a new project and save it at "/tmp/my_project.qgz"
3. Load the vector layer "world_map.gpkg" available in QGIS ("resources/data/world_map.gpkg")
4. Filter "USA" from the field "adm0_a3"
5. Render the map and show me the result
6. Save the project
```

#### Layer management

```text
List all layers in the current project, then add a new vector layer from "/data/roads.gpkg".
Set its visibility to true and zoom to its extent.
```

#### Feature editing with transaction

```text
Start editing the "parcels" layer, add 3 new features with attributes,
commit the edits, and verify the feature count increased.
```

#### Processing with background job

```text
Start a background processing job to buffer the "rivers" layer by 100 meters.
Poll the job status until it completes, then add the result to the project.
```

#### Styling and labeling

```text
Apply a categorized style to the "landuse" layer using the "type" field.
Then add labels showing the "name" attribute with 12pt bold text.
```

#### Layout creation

```text
Create a new print layout called "Map1", add a map item, a title label,
a legend, and a scalebar. Export it as a PDF to "/tmp/map.pdf".
```

#### Multi-instance workflow

```text
List the configured QGIS instances. On the "planning" instance, load the project
at "/data/planning.qgz". On the "archive" instance, export the current project.
```

#### SQL query across layers

```text
Execute SQL to join the "parcels" and "owners" layers:
SELECT p.id, p.area, o.name FROM parcels p JOIN owners o ON p.owner_id = o.id
WHERE p.area > 1000
```

---

## Updating

The plugin (inside QGIS) and the MCP server (outside QGIS) must stay in sync — a newer server sending a command the older plugin doesn't know will return an error. Run `diagnose` after any update to verify both sides match.

| Component | PyPI / Release install | Local install (`git clone`) |
|-----------|------------------------|-----------------------------|
| **QGIS plugin** | Download the new ZIP from [Releases](https://github.com/LuiccianDev/qgis-mcp/releases) and `Install from ZIP` again | `git pull`, then re-run `python install.py` (re-links the plugin) |
| **MCP server** | Force a `uvx` cache refresh with `uvx --refresh luiccian-qgis-mcp`, then restart your MCP client | `git pull`, then restart the MCP server process |

If you run directly from GitHub `master` instead of PyPI, refresh with:
`uvx --refresh-package luiccian-qgis-mcp --from https://github.com/LuiccianDev/qgis-mcp/archive/refs/heads/master.zip luiccian-qgis-mcp`.

After updating the plugin, click **Stop / Start** in the Luiccian QGIS Listener dock widget (or reload via `Plugins` > `Luiccian QGIS Listener` > `Reload Plugin`) to load the new code without restarting QGIS.

---

## Tools (128)

| Category | Tools |
|----------|-------|
| **Project** | `load_project`, `create_new_project`, `save_project`, `get_project_info`, `set_project_crs` |
| **Layers** | `get_layers`, `add_vector_layer`, `add_raster_layer`, `add_web_layer`, `remove_layer`, `find_layer`, `create_memory_layer`, `set_layer_visibility`, `zoom_to_layer`, `get_layer_extent`, `set_layer_property`, `get_layer_crs`, `set_layer_crs`, `get_active_layer`, `set_active_layer`, `add_table_join`, `export_layer` |
| **Features** | `get_layer_features`, `add_features`, `update_features`, `update_feature_geometry`, `delete_features`, `select_features`, `get_selection`, `clear_selection`, `get_field_statistics`, `get_unique_values` |
| **Fields** | `add_field`, `delete_field`, `rename_field`, `field_calculator` |
| **Editing** | `start_editing`, `commit_edits`, `rollback_edits`, `get_edit_status`, `undo_edits`, `redo_edits` |
| **Styling** | `set_layer_style` (single, categorized, graduated), `set_raster_style` (pseudocolor, gray, RGB, hillshade), `apply_style_qml`, `save_style_qml`, `get_layer_labeling`, `set_layer_labeling` |
| **Connections** | `list_connections`, `create_postgresql_connection`, `list_connection_tables`, `add_layer_from_connection`, `import_layer_to_connection`, `execute_connection_sql` |
| **Rendering** | `render_map`, `get_canvas_screenshot`, `get_3d_screenshot`, `get_canvas_extent`, `set_canvas_extent`, `get_canvas_scale`, `set_canvas_scale` |
| **Bookmarks & themes** | `add_bookmark`, `get_bookmarks`, `remove_bookmark`, `add_map_theme`, `get_map_themes`, `apply_map_theme`, `remove_map_theme` |
| **Processing** | `execute_processing`, `execute_processing_batch`, `list_processing_algorithms`, `get_algorithm_help`, `get_processing_providers`, `create_processing_model`, `list_processing_models`, `run_model`, `start_processing_job`, `get_processing_job`, `cancel_processing_job` |
| **Session** | `create_checkpoint`, `list_checkpoints`, `restore_checkpoint`, `export_session` |
| **Analysis** | `raster_calculator`, `zonal_statistics`, `sample_raster_values`, `spatial_join` |
| **Layouts** | `list_layouts`, `export_layout`, `create_layout`, `add_layout_map`, `add_layout_label`, `add_layout_legend`, `add_layout_scalebar`, `add_layout_picture`, `add_layout_table`, `add_layout_grid`, `update_layout_item`, `remove_layout_item`, `get_layout_info`, `remove_layout` |
| **Atlas** | `configure_atlas`, `export_atlas` |
| **Query** | `execute_sql`, `evaluate_expression`, `identify_features` |
| **Layer tree** | `get_layer_tree`, `create_layer_group`, `move_layer_to_group`, `duplicate_layer`, `set_layer_order` |
| **Plugins** | `list_plugins`, `get_plugin_info`, `reload_plugin` |
| **System** | `ping`, `diagnose`, `list_qgis_instances`, `get_qgis_info`, `get_raster_info`, `get_message_log`, `execute_code`, `batch_commands`, `validate_expression`, `get_project_variables`, `set_project_variable`, `get_setting`, `set_setting`, `transform_coordinates` |

All tools are async with human-readable titles and annotations (`readOnly`, `destructive`, `idempotent`). Destructive tools rely on your client's own confirmation gate, which reads the `destructive` annotation; set `QGIS_MCP_AUTO_CONFIRM=0` to have the server elicit a second confirmation as well. Long-running tools report progress via MCP logging.

### Compound tool mode

Set `QGIS_MCP_TOOL_MODE=compound` to reduce the granular tools to 27 grouped tools (every granular command stays reachable), cutting schema overhead per LLM turn. Each compound tool takes an `action` parameter plus a `params` object holding that action's parameters:

```bash
QGIS_MCP_TOOL_MODE=compound uv run --no-sync src/qgis_mcp/server.py
```

```json
{ "action": "load", "params": { "path": "/data/city.qgz" } }
```

Omit `params` for actions that take none (`{"action": "ping"}`).

Groups: `system`, `project`, `layer`, `features`, `selection`, `style`, `canvas`, `render`, `processing`, `code`, `batch`, `layer_tree`, `plugins`, `variables`, `settings`, `expression`, `query`, `transform`, `message_log`, `layer_property`, `field`, `analysis`, `bookmarks`, `map_themes`, `active_layer`.

---

## Configuration

| Environment variable | Default | Description |
|---------------------|---------|-------------|
| `QGIS_MCP_HOST` | `localhost` | Host for socket connection |
| `QGIS_MCP_PORT` | `9878` | Port for socket connection. The QGIS plugin reads it too: set in the environment QGIS is launched from, it overrides the port saved in the plugin's dropdown for that window. |
| `QGIS_MCP_INSTANCES` | _(unset)_ | Address several running QGIS windows from one server. See [Multiple QGIS instances](#multiple-qgis-instances). |
| `QGIS_MCP_TOKEN` | _(unset)_ | Optional shared secret. When set, it overrides the token file and the plugin rejects any command without a matching token. See [Token and authentication](#token-and-authentication). |
| `QGIS_MCP_TRANSPORT` | `stdio` | MCP transport: `stdio` or `streamable-http` |
| `QGIS_MCP_LOG_FILE` | `~/.local/share/qgis-mcp/server.log` | Log file path (empty to disable) |
| `QGIS_MCP_LOG_LEVEL` | `INFO` | File log level |
| `QGIS_MCP_TOOL_MODE` | `granular` | `granular` (128 tools) or `compound` (27 grouped) |
| `QGIS_MCP_AUTO_CONFIRM` | on | Confirmation elicitation on destructive tools (`execute_code`, `remove_layer`, `delete_features`, ...) is skipped by default. Set to `0`/`false`/`no`/`off` to elicit anyway. |

### Token and authentication

By default the socket has **no authentication** — it binds to `localhost` only, but any process on the machine that can reach the port can drive QGIS (including `execute_code`, which runs arbitrary PyQGIS).

The recommended way to turn authentication on is inside the plugin: open **Setup & Configurator** from `Plugins` > `Luiccian QGIS Listener`, then use the **Security** group to **Generate new token** and **Copy** it. The token is stored once, in a per-user file that both halves read:

| OS | Token file |
|----|------------|
| Windows | `%APPDATA%\qgis-mcp\token` |
| Linux / macOS | `$XDG_CONFIG_HOME/qgis-mcp/token` (default `~/.config/qgis-mcp/token`) |

- **Generate new token** rotates it. Both halves read the file on every command, so the new value takes effect on the next one and clients need no reconfiguration.
- **Revoke** deletes the file and disables authentication again. The UI asks before either action.
- A client configured with the old token stops working after a rotation; copy the new value into the client's `env` block only if you set `QGIS_MCP_TOKEN` there.

`QGIS_MCP_TOKEN` still wins when set: put the same value in the environment QGIS runs in *and* in the MCP server's environment (for example in the `env` block of your MCP client config) to keep the secret out of the token file. Unset it in both places to manage the token from the UI.

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": ["luiccian-qgis-mcp"],
      "env": { "QGIS_MCP_TOKEN": "your-long-random-secret" }
    }
  }
}
```

The token is compared in constant time. Binding the plugin to a **non-loopback address** requires a token — the plugin refuses to start on such an address until a token exists (from the file or from `QGIS_MCP_TOKEN`).

### Multiple QGIS instances

One server registration can drive several running QGIS windows. Start each QGIS with the plugin on its own port, then list them in `QGIS_MCP_INSTANCES` as comma-separated `name=port` or `name=host:port` entries.

Set a window's port in the dropdown next to the Luiccian QGIS Listener toolbar button before starting the server. That choice is saved per QGIS profile, so two windows on the same profile would both start on it; launch each with its own `QGIS_MCP_PORT` instead (for example `QGIS_MCP_PORT=9879 qgis`), which overrides the saved port without changing it.

```json
{
  "mcpServers": {
    "qgis": {
      "command": "uvx",
      "args": ["luiccian-qgis-mcp"],
      "env": { "QGIS_MCP_INSTANCES": "default=9878,planning=9879,archive=lab-box:9880" }
    }
  }
}
```

- Every tool takes an optional `instance` argument (`get_layers(instance="planning")`). Omitting it targets `default`, or — when no entry is called `default` — the **first** entry listed.
- `list_qgis_instances` returns the configured names with their host, port, and current reachability.
- Instance names match `[A-Za-z0-9_-]+`; entries without a host use `QGIS_MCP_HOST` (default `localhost`).
- Each instance has its own pooled connection and its own lock, so two QGIS windows can be driven concurrently.
- **Not supported with `QGIS_MCP_TOOL_MODE=compound`.** Compound tools carry no `instance` argument, so configuring more than one instance in compound mode refuses to start.
- `QGIS_MCP_TOKEN` is shared across instances: the same secret must be set in every QGIS.

---

## Contributing

```bash
git clone https://github.com/LuiccianDev/qgis-mcp.git
cd qgis-mcp
uv sync
python install.py   # symlinks plugin + configures your MCP client
```

`install.py` options: `--clients antigravity,claude-desktop`, `--remote` (downloads the latest release plugin ZIP and configures `uvx` instead of `uv run`), `--from-zip [PATH]` (installs the plugin from a ZIP archive instead of symlinking; omit `PATH` to build `dist/qgis_listener_v*.zip`), `--plugin-only` (installs/links only the QGIS plugin and prints manual JSON), `--print-config`, `--list-qgis`, `--profile myprofile`, `--uninstall`.

Known client names: `antigravity`, `claude-desktop`, `claude-code`, `manual`.

> **Windows (Microsoft Store / MSIX Claude Desktop):** `install.py` uses `--directory` instead of `cwd` in generated configs. This is required for Store-installed Claude Desktop, which runs MCP servers in an MSIX sandbox that silently drops `cwd`. If you configure manually, use `uv --directory "/path/to/qgis-mcp" run --no-sync src/qgis_mcp/server.py` — this works on both MSIX and standalone installs.

```bash
# Lint & format check
uv run --no-sync ruff check qgis_listener/ src/ tests/ install.py scripts/
uv run --no-sync ruff format --check qgis_listener/ src/ tests/ install.py scripts/

# Unit tests (no QGIS needed - mocked socket)
uv run --no-sync pytest tests/ --ignore=tests/test_qgis_live.py --ignore=tests/test_stress.py --ignore=tests/test_tdd.py -q

# Integration tests (requires QGIS plugin running)
uv run --no-sync pytest tests/test_qgis_live.py -v
```

---

## License

Luiccian QGIS MCP is developed and maintained by **LuiccianDev** under a **dual-license** structure matching its two-process architecture:

- **MCP server** (`src/qgis_mcp/`) — [Apache License 2.0](LICENSE) (`Apache-2.0`). Runs as a standalone Python process and communicates with QGIS strictly over TCP/JSON.
- **QGIS plugin** (`qgis_listener/`) — [GNU GPL v2 or later](qgis_listener/LICENSE) (`GPL-2.0-or-later`), required for in-process integration with QGIS and PyQGIS.

See [`NOTICE`](NOTICE) for copyright and trademark details.
