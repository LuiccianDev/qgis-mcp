---
name: qgis-mcp-tools
description: Reference guide for using Luiccian QGIS MCP tools, parameters, modes (granular vs compound), MCP resources, and operational limits.
---

# Luiccian QGIS MCP — Tool Reference

Use this skill when calling tools on the `luiccian-qgis-mcp` server to control QGIS via MCP.

## Tool Modes (`QGIS_MCP_TOOL_MODE`)

1. **`granular` mode (default — 128 tools)**:
   - Every QGIS operation is a dedicated async tool (e.g. `get_layers`, `execute_processing`, `set_layer_style`).
   - Every granular tool accepts an optional `instance` parameter (`str | None = None`) to target a specific QGIS window when `QGIS_MCP_INSTANCES` is configured.
2. **`compound` mode (`QGIS_MCP_TOOL_MODE=compound` — 27 tools)**:
   - Reduces schema overhead by grouping operations into 27 domain tools (`system`, `project`, `layer`, `features`, `editing`, `processing`, etc.).
   - Each compound tool takes `action` (string) and `params` (object, omit if the action takes no arguments), e.g. `{"action": "load", "params": {"path": "C:/maps/project.qgz"}}`.
   - Compound mode does **not** expose `instance` selection; configuring multiple instances in compound mode is rejected at startup.

## Multi-Instance Routing

- Call `list_qgis_instances` to discover configured QGIS windows when `QGIS_MCP_INSTANCES` is set (e.g. `default=9878,b=9879`).
- Pass `instance` explicitly on granular tools whenever working across multiple QGIS sessions; omitting it routes to `default` (or the first configured instance).

## Core Parameter Rules & Limits

- **Feature pagination (`get_layer_features`)**:
  - `limit` defaults to `10` and **cannot exceed `50`** (requests above `50` are rejected rather than clamped).
  - Page through large layers with `offset`, or filter server-side using `expression` or `execute_sql`.
  - Returned features are flat dicts with `_fid` and top-level attributes; geometry is placed in `_geometry` when requested.
- **Edit sessions & buffering**:
  - `start_editing`, `commit_edits`, `rollback_edits`, `undo_edits`, `redo_edits`, and `get_edit_status` manage the `QgsVectorLayer` edit buffer.
  - `add_features`, `update_features`, `delete_features`, and `update_feature_geometry` automatically write into the edit buffer when a session is open (`buffered` is `true` in the response) and to the data provider otherwise.
- **Timeouts & long-running work**:
  - `execute_processing`, `execute_processing_batch`, `render_map`, and `execute_code` use a 60s socket timeout with a 55s default plugin deadline (configurable via `timeout`).
  - For heavy Processing algorithms that may exceed 55s, use `start_processing_job` (non-blocking `QgsProcessingAlgRunnerTask`), poll with `get_processing_job`, and cancel with `cancel_processing_job`. Do not pass `NoThreading` algorithms or `TEMPORARY_OUTPUT`/`memory:` sinks with `load_results` disabled.
- **Batching (`batch_commands`)**:
  - Executes a sequence of commands in one round-trip.
  - Cannot nest `batch_commands` and cannot include destructive/blocked commands (`BATCH_BLOCKED_COMMANDS`: `batch`, `execute_code`, `delete_features`, `remove_layer`, `rollback_edits`, `create_new_project`, `remove_layout`, `execute_connection_sql`, `import_layer_to_connection`).
- **Database connections**:
  - `create_postgresql_connection` never accepts a raw password; set `connection_mode` to `endpoint_using_auth_manager`, `service_using_auth_manager`, or `service_only`.

## MCP Resources (Read-Only Context)

Prefer reading MCP resources for zero-side-effect inspection of the implicit QGIS instance:

- `qgis://info` — QGIS version, profile, and plugin count
- `qgis://project` — Current project metadata, CRS, and layer summary
- `qgis://layers` — All layers with IDs, names, types, and visibility
- `qgis://layers/{layer_id}/info` — CRS, extent, fields, feature count, source, and provider
- `qgis://layers/{layer_id}/features` — First 10 sample features
- `qgis://layers/{layer_id}/schema` — Field names, types, and lengths
- `qgis://llms.txt` — Compact server capabilities summary

## Full Tool Catalog

See [tool-catalog.md](references/tool-catalog.md) for all 128 granular tools organized by domain and all 27 compound tools.
