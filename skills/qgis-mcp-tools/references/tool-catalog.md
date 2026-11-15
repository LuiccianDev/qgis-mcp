# Luiccian QGIS MCP — Complete Tool Catalog

## Granular Tools (128)

### System, Connectivity & Settings
- `ping` — Verify socket connectivity to the QGIS plugin
- `diagnose` — Full environment, plugin, and project health check
- `list_qgis_instances` — List configured QGIS instances (`QGIS_MCP_INSTANCES`)
- `get_qgis_info` — QGIS version, profile, and loaded plugin count
- `get_message_log` — Read recent QGIS message log entries
- `list_plugins`, `get_plugin_info`, `reload_plugin` — Inspect or reload QGIS plugins
- `get_setting`, `set_setting` — Read or update QGIS settings (`QgsSettings`)

### Project, Checkpoints & Session
- `get_project_info` — Project title, path, CRS, and layer summary
- `create_new_project`, `load_project`, `save_project` — Project lifecycle
- `set_project_crs` — Set the project Coordinate Reference System
- `get_project_variables`, `set_project_variable` — Project-level expression variables
- `create_checkpoint`, `list_checkpoints`, `restore_checkpoint` — Snapshot and restore project state
- `export_session` — Export the recorded session journal as a reproducible Python script

### Layers, Layer Tree & Properties
- `get_layers`, `find_layer` — List all layers or search by name/pattern
- `add_vector_layer`, `add_raster_layer`, `add_web_layer`, `create_memory_layer` — Add layers
- `duplicate_layer`, `remove_layer` — Clone or remove layers
- `get_active_layer`, `set_active_layer` — Query or switch the active layer
- `set_layer_visibility`, `set_layer_property` — Toggle visibility or configure layer properties
- `get_layer_extent`, `zoom_to_layer` — Inspect layer bounds or zoom canvas to layer
- `get_layer_crs`, `set_layer_crs` — Inspect or assign layer CRS
- `get_layer_tree`, `create_layer_group`, `move_layer_to_group`, `set_layer_order` — Manage layer tree hierarchy
- `add_table_join` — Join an attribute table to a vector layer
- `export_layer` — Export a layer to GeoPackage, Shapefile, GeoJSON, etc.

### Features, Selection & Fields
- `get_layer_features` — Read features (`limit <= 50`, `offset`, `expression`)
- `identify_features` — Spatial identify at a point/coordinates
- `execute_sql` — Run SQL queries over project layers
- `get_field_statistics`, `get_unique_values` — Numeric summary stats and distinct values
- `select_features`, `get_selection`, `clear_selection` — Manage layer feature selection
- `add_field`, `delete_field`, `rename_field`, `field_calculator` — Manage fields and compute values

### Edit Sessions & Feature Mutation
- `start_editing`, `commit_edits`, `rollback_edits`, `get_edit_status`, `undo_edits`, `redo_edits` — Edit buffer and undo stack
- `add_features`, `update_features`, `delete_features`, `update_feature_geometry` — Create, modify, or delete features (buffered when editing is active)

### Symbology, Labeling & Map Themes
- `set_layer_style`, `set_raster_style`, `apply_style_qml`, `save_style_qml` — Vector/raster styling and QML import/export
- `get_layer_labeling`, `set_layer_labeling` — Configure vector feature labels
- `get_map_themes`, `add_map_theme`, `remove_map_theme`, `apply_map_theme` — Manage visibility/style presets

### Canvas, Bookmarks, Rendering & Layouts
- `get_canvas_extent`, `set_canvas_extent`, `get_canvas_scale`, `set_canvas_scale` — Control map viewport
- `get_canvas_screenshot`, `get_3d_screenshot`, `render_map` — Capture viewport or offscreen rendered images
- `get_bookmarks`, `add_bookmark`, `remove_bookmark` — Spatial bookmarks
- `list_layouts`, `create_layout`, `get_layout_info`, `remove_layout`, `export_layout` — Print layout lifecycle and export
- `add_layout_map`, `add_layout_label`, `add_layout_legend`, `add_layout_scalebar`, `add_layout_picture`, `add_layout_table`, `add_layout_grid`, `update_layout_item`, `remove_layout_item` — Print layout items
- `configure_atlas`, `export_atlas` — Atlas generation and batch export

### Processing, Models & Background Jobs
- `get_processing_providers`, `list_processing_algorithms`, `get_algorithm_help` — Discover Processing algorithms
- `execute_processing`, `execute_processing_batch` — Run synchronous Processing algorithms (with `timeout`)
- `start_processing_job`, `get_processing_job`, `cancel_processing_job` — Async background Processing tasks
- `create_processing_model`, `list_processing_models`, `run_model` — Build and execute `.model3` workflows

### Raster, Vector Analysis & Coordinates
- `get_raster_info`, `raster_calculator`, `zonal_statistics`, `sample_raster_values` — Raster inspection and analysis
- `spatial_join` — Join attributes by spatial relationship
- `transform_coordinates` — Transform coordinates between CRSs

### Database Connections
- `list_connections`, `create_postgresql_connection`, `list_connection_tables`, `add_layer_from_connection`, `import_layer_to_connection`, `execute_connection_sql` — Manage saved QGIS Browser database connections

### Expressions, Code & Batch
- `validate_expression`, `evaluate_expression` — Check and evaluate QGIS expressions
- `execute_code` — Execute PyQGIS code inside QGIS (with `timeout`, returns `executed`, `timed_out`, `elapsed`)
- `batch_commands` — Run multiple non-blocked commands sequentially

---

## Compound Tools (`QGIS_MCP_TOOL_MODE=compound` — 27 Tools)

Each tool accepts `action` and optional `params`:

`active_layer`, `analysis`, `batch`, `bookmarks`, `canvas`, `code`, `connection`, `editing`, `expression`, `features`, `field`, `layer`, `layer_property`, `layer_tree`, `map_themes`, `message_log`, `plugins`, `processing`, `project`, `query`, `render`, `selection`, `settings`, `style`, `system`, `transform`, `variables`.
