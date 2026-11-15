# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Expand live integration tests coverage
- Add input validation improvements for MCP tools
- Consider publishing to QGIS Plugin Repository

## [0.1.1] - 2026-11-15

### Added
- pytest-cov to CI for test coverage measurement (Codecov integration)
- Pre-commit hooks for automatic formatting and linting (ruff + flake8)

### Fixed
- Corregido `TypeError` al cargar herramientas: las firmas de `register_tools()` en los módulos de `tools/` ahora coinciden con las llamadas en `tools/__init__.py`.
- Agregados imports faltantes: `ImageContent` y `Annotations` en `canvas.py`, `ProcessingParams` en `processing.py`, `TIMEOUT_LONG` en `vector_analysis.py`, `raster_compute.py`, `export.py` y `rendering.py`, `TransformCoordinatesParams` en `crs.py`, `FeatureQueryParams` en `features.py`.
- Alineadas las firmas de `connectivity`, `connections`, `processing`, `code`, `layers`, `highvalue` y `settings` para recibir los parámetros correctos.

### Changed
- Paquete fuente estructurado bajo `src/qgis_mcp/` (`qgis_mcp`) manteniendo el nombre de distribución y ejecutable `luiccian-qgis-mcp` (`uvx luiccian-qgis-mcp`).
- Linting, formateo y reglas de seguridad (`S`, `C4`, `PIE`) unificados en `pyproject.toml` usando exclusivamente `uv` + `ruff` + `pytest`.
- Umbral de cobertura de tests subido de 60% a 75% en `pyproject.toml`.
- Código formateado con `ruff format` (33 archivos actualizados).
- Aplicados 17 fixes automáticos de `ruff check --fix`.

### Removed
- Eliminados archivos de configuración externos `.flake8` y `.pre-commit-config.yaml` junto con las dependencias/pasos externos de `flake8` y `bandit`.
- Eliminados scripts de debug abandonados: `scripts/debug_extract.py` y `scripts/debug_extract2.py`.

## [0.1.0] - 2026-11-10

First release of Luiccian QGIS MCP.

### Changed
- Distribution named `qgis-mcp` (import package `luiccian_qgis_mcp`), activated via CLI script `luiccian-qgis-mcp`.
- QGIS plugin renamed to `qgis_listener`, shown as **Luiccian QGIS Listener**.
- Default socket port is now `9878`, settings prefix `qgis_mcp`, log file
  `~/.local/share/qgis-mcp/server.log`.
- `QGIS_MCP_*` environment variables are unchanged.

### Added
- Shared token file (`%APPDATA%\qgis-mcp\token` on Windows,
  `$XDG_CONFIG_HOME/qgis-mcp/token` elsewhere) read by both halves, with a
  Security group in the Configurator to generate, copy, rotate and revoke it.
- 125 MCP tools covering:
  - **Project management**: load, create, save, CRS settings
  - **Layer management**: vector/raster/web layers, memory layers, visibility, extent, properties
  - **Feature editing**: add, update, delete, select, geometry updates
  - **Field operations**: add, delete, rename, calculator
  - **Edit sessions**: start, commit, rollback, undo, redo
  - **Styling**: single/categorized/graduated, raster styles, QML import/export, labeling
  - **Database connections**: PostgreSQL, GeoPackage, SpatiaLite, MS SQL via Browser panel
  - **Rendering**: map rendering, canvas screenshots, 3D screenshots
  - **Bookmarks & themes**: add, get, remove, apply
  - **Processing**: algorithms, batches, models, background jobs
  - **Session management**: checkpoints, session export
  - **Analysis**: raster calculator, zonal statistics, spatial join
  - **Layouts & Atlas**: create, export, add maps/labels/legends/scalebars
  - **Query**: SQL, expressions, feature identification
  - **Layer tree**: groups, ordering, duplication
  - **Plugin management**: list, info, reload
  - **System**: ping, diagnose, code execution, batch commands, coordinate transform
- Multi-instance support via `QGIS_MCP_INSTANCES` for addressing multiple QGIS windows
- Compound tool mode (`QGIS_MCP_TOOL_MODE=compound`) reducing 125 tools to 27 grouped tools
- Background processing jobs via `QgsProcessingAlgRunnerTask`
- Session journal and export as reproducible scripts
- Checkpoints with memory layer preservation
- Coordinate transformation with `QgsCoordinateTransform`
- MCP protocol features: logging, elicitation, completions, annotations
- Support for multiple MCP clients: Claude Code, Codex CLI, Gemini CLI, Qwen Code, Kimi Code CLI, GitHub Copilot CLI, opencode, LM Studio, Claude Desktop, Cursor, VS Code, Windsurf, Zed, Hermes

### Notes
- Compatible with QGIS 3.28–4.x
- Plugin must stay Python 3.9-compatible (QGIS ships 3.9)

## Version History

### Key Features by Category

#### Architecture
- Non-blocking TCP socket server driven by QTimer inside QGIS event loop
- Length-prefixed framing protocol over TCP
- Up to 10 concurrent client connections
- Optional shared-secret authentication with constant-time comparison
- Token read on every command (no restart needed for rotation)

#### Security
- Optional token-based authentication
- Non-loopback binding requires token
- MAX_AUTH_FAILURES disconnect after consecutive failures
- Password-redacted connection URIs

#### Performance
- All tools async with human-readable titles
- ToolAnnotations for readOnly/destructive/idempotent hints
- Configurable timeouts (30s default, 60s for long-running)
- Background jobs for long processing tasks
- Connection pooling per instance

#### Error Handling
- Structured error responses with CommandError
- LayerNotFound, WrongLayerType for validation
- Timeout handling without retries (prevents desync)
- Destructive tool confirmation via MCP client gate
