---
name: qgis-mcp-workflows
description: Recommended call chains, safe editing patterns, CRS checks, and best practices for operating QGIS through Luiccian QGIS MCP.
---

# Luiccian QGIS MCP — Workflows & Best Practices

Follow these call chains and safety rules whenever operating QGIS through Luiccian QGIS MCP.

## 1. Preflight & Context Discovery Chain

Before modifying a project or running analysis:

1. Verify connectivity: `ping` (or `diagnose` if troubleshooting connection, auth, or plugin state).
2. If working with multiple QGIS windows, call `list_qgis_instances` and pass `instance` explicitly on every subsequent granular tool call.
3. Inspect the loaded project and layers:
   - `get_project_info` (or resource `qgis://project`)
   - `get_layers` (or resource `qgis://layers`)

## 2. Safe Data Inspection Chain

Never dump an entire layer into context. Inspect structure and summaries first:

1. Read `qgis://layers/{layer_id}/info` and `qgis://layers/{layer_id}/schema` (or `get_raster_info` for rasters).
2. Summarize distributions with `get_field_statistics` (numeric) and `get_unique_values` (categorical).
3. Sample rows with `get_layer_features` (`limit=10`, max `50`), using `expression` for server-side filtering and `offset` for paging, or use `execute_sql` for aggregations.

## 3. Safe Editing & Checkpoint Chain

Protect project state before destructive or bulk edits:

1. Snapshot state with `create_checkpoint` before risky operations (so `restore_checkpoint` can recover).
2. Open an edit session with `start_editing` on the target vector layer.
3. Apply mutations (`add_features`, `update_features`, `delete_features`, `update_feature_geometry`, `field_calculator`). Confirm `buffered` is `true` in responses so edits stay undoable in the edit buffer.
4. Inspect `get_edit_status`, then finalize with `commit_edits` — or revert with `undo_edits` / `rollback_edits`.
5. Optionally call `save_project` once changes are verified.

## 4. CRS-Safe Spatial Analysis & Processing Chain

1. Check CRS on every participating layer with `get_layer_crs` (and project CRS via `get_project_info`).
2. Reproject mismatched layers first (e.g. via `execute_processing` with `native:reprojectlayer`) rather than mixing CRSs in spatial operations.
3. Prefer dedicated tools (`spatial_join`, `zonal_statistics`, `raster_calculator`, `execute_processing`) over `execute_code`.
4. For heavy algorithms that may exceed the 55s plugin deadline, use `start_processing_job` → poll `get_processing_job` (or `cancel_processing_job` to abort).
5. To build a reusable `.model3` workflow, call `create_processing_model` directly — algorithm lookup happens inside the plugin, so do not pre-call `list_processing_algorithms` or `get_algorithm_help` unless debugging a failure.

## 5. Thematic Styling & Cartographic Output Chain

1. Inspect values first (`qgis://layers/{layer_id}/schema`, `get_field_statistics`, `get_unique_values`).
2. Apply symbology and labels: `set_layer_style` (`categorized` for discrete categories, `graduated` for numeric ranges) or `set_raster_style`, plus `set_layer_labeling`.
3. Frame the map (`zoom_to_layer` or `set_canvas_extent` / `set_canvas_scale`) and **visually verify** with `get_canvas_screenshot` or `render_map`.
4. Build print outputs with `create_layout` → `add_layout_map` → `add_layout_legend`, `add_layout_scalebar`, `add_layout_label`, `add_layout_grid` → `export_layout` (or `configure_atlas` + `export_atlas`).

## 6. Database Connections Chain

1. Discover saved Browser connections with `list_connections` and their tables with `list_connection_tables`.
2. Load or query via `add_layer_from_connection`, `import_layer_to_connection`, or `execute_connection_sql`.
3. When creating a PostgreSQL connection via `create_postgresql_connection`, never pass raw passwords; choose `connection_mode` (`endpoint_using_auth_manager`, `service_using_auth_manager`, or `service_only`).

## Anti-Patterns to Avoid

- **Defaulting to `execute_code`**: Always use dedicated MCP tools first; reserve `execute_code` for PyQGIS operations with no dedicated tool.
- **Requesting `limit > 50` in `get_layer_features`**: The server rejects limits above 50; paginate with `offset` or filter with `expression`.
- **Nesting or wrapping blocked commands in `batch_commands`**: `batch_commands` rejects nested batches and destructive commands (`execute_code`, `delete_features`, `remove_layer`, `rollback_edits`, `create_new_project`, `remove_layout`, `execute_connection_sql`, `import_layer_to_connection`).
- **Editing without `start_editing` on important layers**: Writing directly to the provider bypasses `undo_edits` and `rollback_edits`.
- **Skipping visual verification**: Always inspect `get_canvas_screenshot` or `render_map` after styling or layout changes before exporting final deliverables.
