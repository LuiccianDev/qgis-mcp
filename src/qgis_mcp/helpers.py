"""Shared helpers for server.py and compound_tools.py.

Imports only from ``mcp``, stdlib, and the stdlib-only ``protocol``
module - no circular-import risk. Protocol constants live in
``protocol.py`` (and are re-exported here) so the client stays
importable without the ``mcp`` package.
"""

import json

from mcp.types import Annotations, ImageContent, ResourceLink, TextContent

try:
    from mcp.server.fastmcp.exceptions import ToolError
except ImportError:  # mcp >= 2.0 renamed the package
    from mcp.server.mcpserver.exceptions import ToolError

from qgis_mcp.protocol import (  # noqa: F401 - re-exported for server-side importers
    BATCH_BLOCKED_COMMANDS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    HEADER_STRUCT,
    MAX_MESSAGE_SIZE,
    RECV_CHUNK_SIZE,
    TIMEOUT_DEFAULT,
    TIMEOUT_LONG,
    CommandTimeout,
    get_auth_token,
    get_client_version,
    get_update_command,
)

MAX_FEATURE_LIMIT = 50


def feature_limit_error(limit: int) -> str | None:
    """Refusal text for a get_layer_features limit above the cap, else None.

    It used to be clamped to 50 unseen, so a caller asking for 200 read 50
    features as if they were all it asked for.
    """
    if limit > MAX_FEATURE_LIMIT:
        return (
            f"limit {limit} exceeds the maximum of {MAX_FEATURE_LIMIT}; "
            "page through the rest with offset"
        )
    return None


def code_failure_message(result: dict) -> str | None:
    """Error text for an execute_code result whose script raised or timed out, else None.

    The plugin reports a failed script as a successful command with
    ``executed: False``; the MCP tools raise this text as a ToolError so the
    client sees ``isError`` and still gets the traceback and partial output.
    """
    if result.get("executed", True):
        return None
    parts = [
        f"Code failed after {result.get('elapsed', '?')}s: {result.get('error', 'unknown error')}"
    ]
    for key in ("traceback", "stdout", "stderr"):
        if result.get(key):
            parts.append(f"{key}:\n{result[key].rstrip()}")
    if not result.get("timed_out"):
        parts.append("Changes the script made before it failed are kept.")
    return "\n\n".join(parts)


def enrich_diagnose(result: dict) -> dict:
    """Append server/plugin version-match check to a diagnose result."""
    server_version = get_client_version()
    if server_version == "unknown":
        server_version = "unknown (editable install?)"

    plugin_version = None
    for check in result.get("checks", []):
        if check["name"] == "plugin_version":
            plugin_version = check.get("detail")
            break

    version_match = "ok" if plugin_version == server_version else "mismatch"
    detail = {"server": server_version, "plugin": plugin_version}
    if version_match == "mismatch":
        # The whole point of reporting a mismatch is that someone can act on it.
        # Say what it actually costs, too: mismatched halves keep working, and a
        # report that reads like an outage gets ignored the next time it matters.
        detail["fix"] = get_update_command()
        detail["restart_after_fix"] = True
        detail["note"] = (
            "Not fatal. Mismatched halves keep working; tools added since the "
            "older half was built will be missing or refused, so matching them "
            "is recommended rather than required. Restart your MCP client after "
            "running the fix."
        )
    # An older plugin's diagnose may not carry either key, and this check is the
    # one that reports exactly that kind of drift - it must not raise on it.
    result.setdefault("checks", []).append(
        {"name": "version_match", "status": version_match, "detail": detail}
    )
    if version_match == "mismatch" and result.get("status") == "healthy":
        result["status"] = "degraded"

    return result


def make_layer_response(result: dict, fallback_name: str = "Layer") -> list:
    """Build [TextContent, ResourceLink] for a layer-mutating tool response."""
    layer_id = result.get("layer_id", result.get("id", ""))
    return [
        TextContent(type="text", text=json.dumps(result)),
        ResourceLink(
            type="resource_link",
            uri=f"qgis://layers/{layer_id}/info",
            name=result.get("name", fallback_name),
        ),
    ]


def make_project_response(result: dict) -> list:
    """Build [TextContent, ResourceLink] for a project-mutating tool response."""
    return [
        TextContent(type="text", text=json.dumps(result)),
        ResourceLink(type="resource_link", uri="qgis://project", name="Project Info"),
    ]


def checked_timeout(timeout: int) -> int:
    """Return *timeout* when it is a whole number of seconds in 1..600, else raise ToolError.

    The socket timeout is derived as ``timeout + 5``; a value of 0 or less made
    that non-positive, and ``socket.settimeout`` then raised a ValueError that
    the client reported as a protocol framing error.
    """
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise ToolError(
            f"timeout must be a whole number of seconds between 1 and 600, got {timeout!r}"
        )
    return timeout


def image_data(result: dict) -> str:
    """The base64 PNG in a plugin image response, or ToolError when it is absent."""
    data = result.get("base64_data") if isinstance(result, dict) else None
    if not data:
        raise ToolError("QGIS returned no image data")
    return data


def make_image_response(result: dict) -> list[ImageContent]:
    """Build a single-element [ImageContent] list from a plugin PNG payload."""
    return [
        ImageContent(
            type="image",
            data=image_data(result),
            mimeType="image/png",
            annotations=Annotations(audience=["user", "assistant"], priority=1.0),
        )
    ]


def make_render_response(result: dict, width: int, height: int, path: str | None) -> list:
    """Build [ImageContent, optional TextContent] for a render_map response."""
    content: list = list(make_image_response(result))
    info: dict = {}
    if path:
        info.update({"saved": path, "width": width, "height": height})
    if result.get("warnings"):
        # Layers that failed to draw; the image alone looks like a clean render.
        info["warnings"] = result["warnings"]
    if info:
        content.append(
            TextContent(
                type="text",
                text=json.dumps(info),
                annotations=Annotations(audience=["assistant"], priority=0.5),
            )
        )
    return content


LLMS_CONTEXT_TEXT = """# QGIS MCP - LLM Context

## Overview
QGIS MCP connects QGIS Desktop to LLMs via the Model Context Protocol.
125 tools for project management, layer operations, feature editing, styling, processing, and more.

## Quick Start
1. `ping` - verify connectivity
2. `diagnose` - check full stack health (versions, providers, clients)
3. `get_project_info` - understand current project
4. `get_layers` - list available layers
5. `get_layer_features` - inspect data (expression filtering, pagination)
6. `render_map` or `get_canvas_screenshot` - see the map

## Tool Categories
- **Info**: ping, diagnose, get_qgis_info, get_project_info
- **Project**: load_project, create_new_project, save_project, set_project_crs
- **Layers**: get_layers, add_vector_layer, add_raster_layer, add_web_layer, remove_layer, find_layer, create_memory_layer
- **Active Layer**: get_active_layer, set_active_layer
- **Visibility**: set_layer_visibility, zoom_to_layer
- **Features**: get_layer_features (max 50, filter with expressions), get_field_statistics, add_table_join
- **Fields**: add_field, delete_field, rename_field
- **Editing**: add_features, update_features, update_feature_geometry, delete_features
- **Edit sessions**: start_editing, commit_edits, rollback_edits, get_edit_status, undo_edits, redo_edits (feature writes are buffered and undoable while a session is open)
- **Selection**: select_features, get_selection, clear_selection
- **Styling**: set_layer_style (single/categorized/graduated, vector only), set_raster_style (singleband_pseudocolor/singleband_gray/multiband_color/hillshade), apply_style_qml, save_style_qml
- **Labeling**: get_layer_labeling, set_layer_labeling (field, font_size, color)
- **Canvas**: get_canvas_extent, set_canvas_extent, get_canvas_screenshot, get_canvas_scale, set_canvas_scale
- **Raster**: get_raster_info
- **Processing**: execute_processing, list_processing_algorithms, get_algorithm_help, create_processing_model
- **Background jobs**: start_processing_job, get_processing_job, cancel_processing_job (no time limit, QGIS stays usable)
- **Session**: create_checkpoint, list_checkpoints, restore_checkpoint (undo a whole sequence of changes), export_session (replayable PyQGIS script)
- **Rendering**: render_map (re-render to image), get_canvas_screenshot (fast grab)
- **Code**: execute_code (arbitrary PyQGIS)
- **Batch**: batch_commands (multiple commands in one round-trip)
- **Layouts**: list_layouts, export_layout, create_layout, add_layout_map, add_layout_label, add_layout_legend, add_layout_scalebar, add_layout_picture, add_layout_table, get_layout_info, remove_layout
- **Atlas**: configure_atlas (coverage layer), export_atlas (one page per feature)
- **Query**: execute_sql (SQL across layers via virtual layer), evaluate_expression (scalar/aggregate), identify_features (features at a point)
- **Layer mgmt**: duplicate_layer, set_layer_order
- **Logging**: get_message_log
- **Plugins**: list_plugins, get_plugin_info, reload_plugin
- **Layer Tree**: get_layer_tree, create_layer_group, move_layer_to_group
- **Properties**: set_layer_property, get_layer_extent
- **CRS**: get_layer_crs, set_layer_crs, transform_coordinates
- **Variables**: get_project_variables, set_project_variable
- **Expression**: validate_expression, evaluate_expression
- **Settings**: get_setting, set_setting
- **Bookmarks**: get_bookmarks, add_bookmark, remove_bookmark
- **Map Themes**: get_map_themes, add_map_theme, remove_map_theme, apply_map_theme
- **Connections**: list_connections, create_postgresql_connection, list_connection_tables, add_layer_from_connection, import_layer_to_connection, execute_connection_sql (saved PostgreSQL/GeoPackage/... connections from the Browser panel)

## Tips
- **World basemap**: QGIS ships with a built-in world map. In the QGIS UI, \
type "world" in the locator bar (bottom of screen) to find and open it. Via MCP: \
use `execute_code` to resolve `QgsApplication.pkgDataPath() + "/resources/data/world_map.gpkg"`, \
then pass that path to `add_vector_layer` to load it as a background for spatial context.
- **Map themes**: save/restore layer visibility presets - useful for toggling between views.
- **Bookmarks**: save named extents for quick navigation to areas of interest.

## Key Patterns
- Layer IDs are used to reference layers (get them from get_layers or find_layer)
- Features are flat dicts: {"_fid": 1, "name": "Berlin", "_geometry": "POINT(...)"}
- Use expressions for server-side filtering: "population > 1000000"
- Processing algorithms: search with list_processing_algorithms, get params with get_algorithm_help
- render_map returns inline images; get_canvas_screenshot is faster (no re-render)
- Destructive operations (remove_layer, delete_features, set_setting) may ask for confirmation
- Use diagnose to troubleshoot connection or version issues

## Resources (read-only data)
- qgis://info - QGIS version info
- qgis://project - project metadata
- qgis://layers - all layers
- qgis://layers/{id}/info - layer details
- qgis://layers/{id}/features - sample features
- qgis://layers/{id}/schema - field schema
- qgis://llms.txt - this context file

## Multiple QGIS Instances
One MCP server can address several running QGIS windows. They are configured with \
`QGIS_MCP_INSTANCES` (e.g. `default=9878,b=9879`); pass `instance="b"` to any tool to \
target that window. Omitting the argument targets the instance named `default`. Call \
`list_qgis_instances` for the configured names, their host/port, and whether each is \
currently reachable - a name that is not configured is rejected with the valid names.

## Environment Variables
- QGIS_MCP_HOST - server host (default: localhost)
- QGIS_MCP_PORT - server port (default: 9878)
- QGIS_MCP_INSTANCES - comma-separated "name=port" or "name=host:port" list of QGIS \
instances (default: unset = a single instance named "default" from QGIS_MCP_HOST/PORT)
- QGIS_MCP_TOKEN - optional shared secret; when set, must match the plugin's value (default: unset = no auth)
- QGIS_MCP_TRANSPORT - "stdio" (default) or "streamable-http"
- QGIS_MCP_TOOL_MODE - "granular" (default, 125 tools) or "compound" (27 grouped tools)
- QGIS_MCP_LOG_FILE - log file path (default: ~/.local/share/qgis-mcp/server.log)
- QGIS_MCP_LOG_LEVEL - file log level (default: INFO)
"""
