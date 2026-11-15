"""High-Value Capabilities tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import CanvasScaleParams


class HighValueToolset(BaseToolset):
    """MCP toolset for active layer, canvas scale, labeling, layer/project CRS, bookmarks, and themes."""

    domain = "highvalue"

    def _register_layer_and_canvas_tools(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Get Active Layer",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get the currently active (selected) layer in the QGIS layer panel.",
            structured_output=True,
        )
        async def get_active_layer(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("get_active_layer", instance=instance)

        @mcp.tool(
            title="Set Active Layer",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Set the active layer in the QGIS layer panel by layer ID.",
        )
        async def set_active_layer(
            ctx: Context, layer_id: str, instance: str | None = None
        ) -> dict:
            return await _send("set_active_layer", {"layer_id": layer_id}, instance=instance)

        @mcp.tool(
            title="Get Canvas Scale",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get the current map canvas scale, rotation, and magnification factor.",
            structured_output=True,
        )
        async def get_canvas_scale(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("get_canvas_scale", instance=instance)

        @mcp.tool(
            title="Set Canvas Scale",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Set the map canvas scale and/or rotation. Provide scale as denominator "
            "(e.g. 50000 for 1:50000). Rotation in degrees (0-360).",
        )
        async def set_canvas_scale(
            ctx: Context,
            scale: float | None = None,
            rotation: float | None = None,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {}
            if scale is not None:
                validated = self.validate(CanvasScaleParams, scale=scale)
                params["scale"] = validated.scale
            if rotation is not None:
                params["rotation"] = rotation
            return await _send("set_canvas_scale", params, instance=instance)

        @mcp.tool(
            title="Get Layer Labeling",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get the labeling configuration of a vector layer: enabled state, field, font size, color.",
            structured_output=True,
        )
        async def get_layer_labeling(
            ctx: Context,
            layer_id: str,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send("get_layer_labeling", {"layer_id": layer_id}, instance=instance)

        @mcp.tool(
            title="Set Layer Labeling",
            description="Configure labeling for a vector layer. Set enabled=false to disable labels. "
            "Set field_name to the attribute field to label with. Optional: font_size (float), "
            "color (hex like '#000000').",
        )
        async def set_layer_labeling(
            ctx: Context,
            layer_id: str,
            enabled: bool = True,
            field_name: str | None = None,
            font_size: float | None = None,
            color: str | None = None,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {"layer_id": layer_id, "enabled": enabled}
            if field_name is not None:
                params["field_name"] = field_name
            if font_size is not None:
                params["font_size"] = font_size
            if color is not None:
                params["color"] = color
            return await _send("set_layer_labeling", params, instance=instance)

    def _register_crs_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        make_project_response = self.context.make_project_response

        @mcp.tool(
            title="Get Layer CRS",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get the coordinate reference system (CRS) of a layer: EPSG code, description, "
            "whether geographic, and PROJ4 string.",
            structured_output=True,
        )
        async def get_layer_crs(
            ctx: Context, layer_id: str, instance: str | None = None
        ) -> dict[str, Any]:
            return await _send("get_layer_crs", {"layer_id": layer_id}, instance=instance)

        @mcp.tool(
            title="Set Layer CRS",
            description="Set the CRS of a layer (e.g. 'EPSG:4326'). This does NOT reproject data - "
            "it only changes how the layer's coordinates are interpreted.",
        )
        async def set_layer_crs(
            ctx: Context, layer_id: str, crs: str, instance: str | None = None
        ) -> dict:
            return await _send(
                "set_layer_crs", {"layer_id": layer_id, "crs": crs}, instance=instance
            )

        @mcp.tool(
            title="Set Project CRS",
            description="Set the project coordinate reference system (e.g. 'EPSG:4326', 'EPSG:3857'). "
            "This changes how layers are projected on the map canvas.",
        )
        async def set_project_crs(ctx: Context, crs: str, instance: str | None = None) -> list:
            result = await _send("set_project_crs", {"crs": crs}, instance=instance)
            return make_project_response(result)

    def _register_bookmark_and_theme_tools(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Get Bookmarks",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get spatial bookmarks from the project. Each bookmark has a name, group, "
            "extent (xmin/ymin/xmax/ymax), and CRS.",
            structured_output=True,
        )
        async def get_bookmarks(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("get_bookmarks", instance=instance)

        @mcp.tool(
            title="Add Bookmark",
            description="Add a spatial bookmark to the project for quick navigation. "
            "Provide a name and extent (xmin/ymin/xmax/ymax), in crs when given, else the project "
            "CRS.",
        )
        async def add_bookmark(
            ctx: Context,
            name: str,
            xmin: float,
            ymin: float,
            xmax: float,
            ymax: float,
            crs: str | None = None,
            group: str = "",
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {
                "name": name,
                "xmin": xmin,
                "ymin": ymin,
                "xmax": xmax,
                "ymax": ymax,
                "group": group,
            }
            if crs:
                params["crs"] = crs
            return await _send("add_bookmark", params, instance=instance)

        @mcp.tool(
            title="Remove Bookmark",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Remove a spatial bookmark by its ID.",
        )
        async def remove_bookmark(
            ctx: Context, bookmark_id: str, instance: str | None = None
        ) -> dict:
            return await _send("remove_bookmark", {"bookmark_id": bookmark_id}, instance=instance)

        @mcp.tool(
            title="Get Map Themes",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get map themes (visibility presets). Each theme stores which layers are visible.",
            structured_output=True,
        )
        async def get_map_themes(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("get_map_themes", instance=instance)

        @mcp.tool(
            title="Add Map Theme",
            description="Create a map theme from the current layer visibility state. "
            "If a theme with this name exists, it will be updated.",
        )
        async def add_map_theme(ctx: Context, name: str, instance: str | None = None) -> dict:
            return await _send("add_map_theme", {"name": name}, instance=instance)

        @mcp.tool(
            title="Remove Map Theme",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Remove a map theme by name.",
        )
        async def remove_map_theme(ctx: Context, name: str, instance: str | None = None) -> dict:
            return await _send("remove_map_theme", {"name": name}, instance=instance)

        @mcp.tool(
            title="Apply Map Theme",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Apply a map theme - restores the layer visibility state saved in the theme.",
        )
        async def apply_map_theme(ctx: Context, name: str, instance: str | None = None) -> dict:
            return await _send("apply_map_theme", {"name": name}, instance=instance)

    def register(self) -> None:
        self._register_layer_and_canvas_tools()
        self._register_crs_tools()
        self._register_bookmark_and_theme_tools()
