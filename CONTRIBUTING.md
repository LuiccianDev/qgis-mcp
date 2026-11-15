# Contributing to Luiccian QGIS MCP

Thank you for your interest in contributing! 🎉
This project connects [QGIS](https://qgis.org/) to any AI agent that speaks the
[Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/getting-started/intro).
Your help in improving this integration is very welcome.

## Getting Started

1. **Fork and clone**

   ```bash
   git clone git@github.com:YOUR-USERNAME/qgis-mcp.git
   cd qgis-mcp
   ```

2. **Install prerequisites**

   - QGIS 3.28 or newer (3.28 to 4.x)
   - Python 3.12 or newer
   - [uv](https://docs.astral.sh/uv/getting-started/installation/)

   On macOS:

   ```bash
   brew install uv
   ```

   On Windows PowerShell:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

3. **Run the installer**

   ```bash
   python install.py
   ```

   It symlinks `qgis_listener/` into your QGIS profile, sets up the venv, and
   writes the MCP client config for whichever clients you pick from the menu.
   Non interactive variant:

   ```bash
   python install.py --non-interactive --clients claude-desktop,cursor
   ```

   Then restart QGIS, open `Plugins` > `Manage and Install Plugins`, and enable
   **Luiccian QGIS Listener**.

## Development Workflow

- Start the plugin server (`Plugins` > `Luiccian QGIS Listener` > `Start Server`).
- Make your changes, then run the tests and the linters:

  ```bash
  uv run --no-sync pytest tests/
  uv run --no-sync ruff check qgis_listener/ src/ tests/ install.py scripts/
  ```

  `tests/test_qgis_live.py` needs a plugin server listening on `localhost:9878`;
  every other test runs against a mocked socket.

- Run `ruff format` before committing; CI checks it with `--check`:

  ```bash
  uv run --no-sync ruff format qgis_listener/ src/ tests/ install.py scripts/
  ```

## Release

The version lives in three places and they must agree before a tag:

1. `pyproject.toml` (`version = "X.Y.Z"`), `qgis_listener/metadata.txt`
   (`version=X.Y.Z`) and the local entry in `uv.lock`. Run `uv lock` after
   editing the first two so the lock file records the new version.
2. Add a `CHANGELOG.md` entry for the release.
3. Fast-forward `dev` into `main` (releases are cut from `main`), then tag:

   ```bash
   git checkout main
   git merge --ff-only dev
   git tag vX.Y.Z
   git push origin main --tags
   ```

The `Release` workflow checks that the tag matches both declared versions and
attaches `qgis_listener_vX-Y-Z.zip` to the GitHub release. There is no Plugin
Repository upload: the plugin is installed with QGIS's **Install from ZIP**.

Before tagging, install the ZIP into a clean profile and run
`tests/test_qgis_live.py` against it.

## Adding a new MCP tool

Every tool has two halves that must stay in sync:

1. **Plugin handler** (`qgis_listener/handlers/`) — the method that runs inside QGIS.
2. **Pydantic validation model** (`src/qgis_mcp/validation.py`) — parameter constraints and validators.
3. **MCP tool** (`src/qgis_mcp/tools/`) — the async method registered inside the domain `<Domain>Toolset(BaseToolset)` class.

There is no dispatch table to update — `@command` registers the name automatically.

### Step 1 — Write the plugin handler

Pick the mixin file for your domain in `qgis_listener/handlers/`:

| Domain | File | Example commands |
|--------|------|-----------------|
| Project | `project.py` | `load_project`, `save_project` |
| Layers | `layers.py` | `add_vector_layer`, `remove_layer` |
| Features | `features.py` | `add_features`, `delete_features` |
| Style | `style.py` | `set_layer_style`, `apply_style_qml` |
| Canvas | `canvas.py` | `get_canvas_extent`, `set_canvas_scale` |
| Processing | `processing.py` | `execute_processing`, `list_processing_algorithms` |
| Layout | `layout.py` | `create_layout`, `export_layout` |
| Connections | `connections.py` | `list_connections`, `execute_connection_sql` |
| Session | `session.py` | `create_checkpoint`, `export_session` |
| System | `system.py` | `ping`, `diagnose`, `execute_code` |

Add the method to the appropriate mixin class, decorate it with `@command`, and return a `dict`:

```python
from ..registry import command

class LayerHandlers:
    @command
    def my_new_command(self, layer_id, **kwargs):
        """Brief docstring describing what the command does."""
        layer = self._layer(layer_id)  # raises LayerNotFound if missing
        # ... do work ...
        return {"success": True, "detail": "something happened"}
```

Rules:
- The plugin must stay **Python 3.9-compatible** (QGIS ships 3.9). Use the tuple form for `isinstance` checks: `isinstance(value, (int, float))`, not `isinstance(value, int | float)`.
- Never use legacy PyQGIS or PyQt5 APIs:
  - Resolve Qt5/Qt6 and QGIS 3.28–4.x enums through `qgis_listener/compat.py` (for example `MAP_LAYER_VECTOR`, `RENDER_UNIT_POINTS`, `MSG_INFO`).
  - Never call `.exec_()` on Qt dialogs or loops; use `.exec()`.
  - Never call `crs.toProj4()` directly (use `crs.toProj() if hasattr(crs, "toProj") else crs.toProj4()`), and never use deprecated `QgsLayoutItemLabel.setFontColor()` (use `QgsTextFormat` + `setTextFormat()`).
  - Always clean up temporary `QgsPrintLayout` instances via `layout.deleteLater()` in a `finally:` block.
- Use `..` imports for package-root modules (`from ..errors import CommandError`), never import sibling handlers.
- Use `self._layer(layer_id)`, `self._get_vector_layer(layer_id)`, `self._get_raster_layer(layer_id)`, and `self._parse_crs(crs)` from `HandlerBase` for lookups and CRS validation.
- Raise `CommandError` for validation failures; `LayerNotFound` and `WrongLayerType` for layer issues.

### Step 2 — Define Pydantic validation & write the MCP tool

If the tool accepts constrained inputs or structured objects, add or reuse a `pydantic.BaseModel` schema in `src/qgis_mcp/validation.py`, then register the `async def` tool inside the matching `<Domain>Toolset(BaseToolset)` class in `src/qgis_mcp/tools/<domain>.py` (connected to `ServerContext`):

```python
from qgis_mcp.tools.base import BaseToolset
from qgis_mcp.validation import MyNewCommandParams

class LayerToolset(BaseToolset):
    domain = "layers"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="My New Command",
            annotations=ToolAnnotations(readOnlyHint=True),  # or destructiveHint=True
            description="Describe what the tool does for the agent.",
            structured_output=True,
        )
        async def my_new_command(
            ctx: Context,
            layer_id: str = Field(description="The layer ID"),
            instance: str | None = None,
        ) -> dict[str, Any]:
            validated = self.validate(MyNewCommandParams, layer_id=layer_id)
            return await _send(
                "my_new_command",
                {"layer_id": validated.layer_id},
                instance=instance,
            )
```

Rules:
- Validate constrained parameters with Pydantic models from `src/qgis_mcp/validation.py` via `self.validate(...)` / `validate_params(...)` so `ValidationError` raises `ToolError`.
- Organize tools inside `<Domain>Toolset(BaseToolset)` classes rather than standalone closures; keep functions small, clean, and well-structured.
- Every tool must be `async def` to support `await ctx.info()` for MCP logging.
- Always include `instance: str | None = None` as the last parameter and forward it to `_send()`.
- Use `ToolAnnotations` to mark `readOnlyHint=True`, `destructiveHint=True`, or `idempotent=True`.
- For destructive tools, call `_confirm_destructive(ctx)` before `_send()` if you want server-side elicitation.
- Use `title=` in `@mcp.tool` for human-readable names.
- Long-running tools (processing, code execution) use `timeout=self.context.timeout_long` (60s) in `_send()`.

### Step 3 — Add a test

In `tests/`, add a test for the new tool:

```python
def test_my_new_command(mock_server):
    result = mock_server.my_new_command(layer_id="test_layer")
    assert result["success"] is True
```

For plugin-dependent tests, declare the module in `PLUGIN_TESTS` in `tests/conftest.py`. For plugin-free tests, use `PLUGIN_FREE_TESTS`.

### Step 4 — Verify parity

Run the structure test to verify both halves are in sync:

```bash
uv run --no-sync pytest tests/test_plugin_structure.py -v
```

This test enforces:
- Every `@command` in the plugin has a matching `@mcp.tool` in the server.
- Every `@mcp.tool` has a matching `@command` in the plugin.
- Handlers don't import each other (only `..` imports).

### Step 5 — Run the full test suite

```bash
uv run --no-sync pytest tests/ -q
uv run --no-sync ruff check qgis_listener/ src/ tests/ install.py scripts/
uv run --no-sync ruff format --check qgis_listener/ src/ tests/ install.py scripts/
```

## Contributing Guidelines

- Keep PRs focused on a single change.
- Write clear commit messages.
- Update docs if behavior changes.
- Be cautious when using `execute_code` (it runs arbitrary PyQGIS).
- **Respect the license boundary**: `src/qgis_mcp/` is **Apache-2.0** and must never import `qgis`, `PyQt5`, `PyQt6`, `sip`, or `qgis_listener`; `qgis_listener/` is **GPL-2.0-or-later** (`license=GPLv2+` in `qgis_listener/metadata.txt`) for in-process PyQGIS integration.

## Reporting Issues

- Use [GitHub Issues](https://github.com/LuiccianDev/qgis-mcp/issues).
- Include OS, QGIS version, and error logs where relevant.
