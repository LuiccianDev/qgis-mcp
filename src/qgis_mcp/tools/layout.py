"""Print Layouts tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import (
    LayoutExportParams,
    LayoutGridParams,
    RemoveLayoutItemParams,
    UpdateLayoutItemParams,
)


class LayoutToolset(BaseToolset):
    """MCP toolset for print layouts, layout items, and atlas configuration/export."""

    domain = "layout"

    def _register_layout_core_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        _confirm_destructive = self._confirm_destructive

        @mcp.tool(
            title="List Layouts",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List all print layouts in the current project with names and page counts.",
            structured_output=True,
        )
        async def list_layouts(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("list_layouts", instance=instance)

        @mcp.tool(
            title="Export Layout",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Export a print layout to file. format: 'pdf', 'png', 'jpg', 'svg'. "
            "dpi: resolution (default 300).",
        )
        async def export_layout(
            ctx: Context,
            layout_name: str,
            path: str,
            format: str = "pdf",
            dpi: int = 300,
            instance: str | None = None,
        ) -> dict:
            validated = self.validate(
                LayoutExportParams, layout_name=layout_name, path=path, dpi=dpi
            )
            return await _send(
                "export_layout",
                {
                    "layout_name": validated.layout_name,
                    "path": validated.path,
                    "format": format,
                    "dpi": validated.dpi,
                },
                instance=instance,
            )

        @mcp.tool(
            title="Create Layout",
            description="Create a new print layout. page_size: e.g. 'A4', 'A3', 'Letter'. "
            "orientation: 'landscape' or 'portrait'.",
        )
        async def create_layout(
            ctx: Context,
            name: str,
            page_size: str = "A4",
            orientation: str = "landscape",
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "create_layout",
                {"name": name, "page_size": page_size, "orientation": orientation},
                instance=instance,
            )

        @mcp.tool(
            title="Get Layout Info",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List items in a print layout (type, id, uuid, position, size) and page count.",
            structured_output=True,
        )
        async def get_layout_info(
            ctx: Context,
            layout_name: str,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send("get_layout_info", {"layout_name": layout_name}, instance=instance)

        @mcp.tool(
            title="Remove Layout",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Remove a print layout from the project.",
        )
        async def remove_layout(
            ctx: Context, layout_name: str, instance: str | None = None
        ) -> dict:
            if not await _confirm_destructive(ctx, f"Remove layout '{layout_name}'?"):
                return {"ok": False, "message": "Cancelled by user"}
            return await _send("remove_layout", {"layout_name": layout_name}, instance=instance)

    def _register_layout_map_and_text_tools(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Add Layout Map",
            description="Add a map item to a print layout at specified position and size (in millimeters). "
            "Optional extent=[xmin, ymin, xmax, ymax] and scale override the canvas view.",
        )
        async def add_layout_map(
            ctx: Context,
            layout_name: str,
            x: float,
            y: float,
            width: float,
            height: float,
            extent: list[float] | None = None,
            scale: float | None = None,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {
                "layout_name": layout_name,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            }
            if extent is not None:
                params["extent"] = extent
            if scale is not None:
                params["scale"] = scale
            return await _send("add_layout_map", params, instance=instance)

        @mcp.tool(
            title="Add Layout Label",
            description="Add a text label to a print layout (mm). text may contain [% expression %] "
            "for dynamic content. color is hex (e.g. '#000000').",
        )
        async def add_layout_label(
            ctx: Context,
            layout_name: str,
            text: str,
            x: float = 10,
            y: float = 10,
            width: float = 100,
            height: float = 20,
            font_size: int = 12,
            color: str = "#000000",
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "add_layout_label",
                {
                    "layout_name": layout_name,
                    "text": text,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "font_size": font_size,
                    "color": color,
                },
                instance=instance,
            )

        @mcp.tool(
            title="Add Layout Legend",
            description="Add a legend to a print layout, linked to a map item (defaults to the first "
            "map item). Position/size in mm. Optional layer_ids restricts the legend to specific layers.",
        )
        async def add_layout_legend(
            ctx: Context,
            layout_name: str,
            map_item_id: str | None = None,
            x: float = 10,
            y: float = 10,
            width: float = 80,
            height: float = 100,
            title: str = "Legend",
            layer_ids: list[str] | None = None,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {
                "layout_name": layout_name,
                "map_item_id": map_item_id,
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "title": title,
            }
            if layer_ids is not None:
                params["layer_ids"] = layer_ids
            return await _send("add_layout_legend", params, instance=instance)

    def _register_layout_graphic_and_table_tools(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Add Layout Scale Bar",
            description="Add a scale bar to a print layout, linked to a map item. style e.g. "
            "'Single Box', 'Double Box', 'Line Ticks Up', 'Numeric'.",
        )
        async def add_layout_scalebar(
            ctx: Context,
            layout_name: str,
            map_item_id: str | None = None,
            x: float = 10,
            y: float = 180,
            width: float = 80,
            height: float = 20,
            style: str = "Single Box",
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "add_layout_scalebar",
                {
                    "layout_name": layout_name,
                    "map_item_id": map_item_id,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "style": style,
                },
                instance=instance,
            )

        @mcp.tool(
            title="Add Layout Picture",
            description="Add a picture or SVG (logo, north arrow) to a print layout. path is an image "
            "or SVG file path. Position/size in mm.",
        )
        async def add_layout_picture(
            ctx: Context,
            layout_name: str,
            path: str,
            x: float = 10,
            y: float = 10,
            width: float = 30,
            height: float = 30,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "add_layout_picture",
                {
                    "layout_name": layout_name,
                    "path": path,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                },
                instance=instance,
            )

        @mcp.tool(
            title="Add Layout Table",
            description="Add an attribute table for a vector layer to a print layout. "
            "max_rows caps the number of features shown. Position/size in mm.",
        )
        async def add_layout_table(
            ctx: Context,
            layout_name: str,
            layer_id: str,
            x: float = 10,
            y: float = 10,
            width: float = 180,
            height: float = 80,
            max_rows: int = 20,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "add_layout_table",
                {
                    "layout_name": layout_name,
                    "layer_id": layer_id,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "max_rows": max_rows,
                },
                instance=instance,
            )

    def _register_atlas_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="Configure Atlas",
            description="Configure a print layout's atlas: coverage_layer (vector layer id) drives one "
            "page per feature. Optional page_name_expression, filter_expression, sort_expression.",
        )
        async def configure_atlas(
            ctx: Context,
            layout_name: str,
            coverage_layer: str,
            enabled: bool = True,
            page_name_expression: str | None = None,
            filter_expression: str | None = None,
            sort_expression: str | None = None,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "configure_atlas",
                {
                    "layout_name": layout_name,
                    "coverage_layer": coverage_layer,
                    "enabled": enabled,
                    "page_name_expression": page_name_expression,
                    "filter_expression": filter_expression,
                    "sort_expression": sort_expression,
                },
                instance=instance,
            )

        @mcp.tool(
            title="Export Atlas",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Export a configured atlas. format 'pdf' writes a single multi-page file at "
            "output_path; image formats ('png','jpg','tif') write one file per feature into the "
            "output_path directory. Call configure_atlas first.",
        )
        async def export_atlas(
            ctx: Context,
            layout_name: str,
            output_path: str,
            format: str = "pdf",
            dpi: int = 300,
            instance: str | None = None,
        ) -> dict:
            await ctx.info(f"Exporting atlas '{layout_name}' as {format} to {output_path}")
            return await _send(
                "export_atlas",
                {
                    "layout_name": layout_name,
                    "output_path": output_path,
                    "format": format,
                    "dpi": dpi,
                },
                timeout=timeout_long,
                instance=instance,
            )

    def _register_layout_item_management_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        _confirm_destructive = self._confirm_destructive

        @mcp.tool(
            title="Add Layout Grid",
            description="Add a coordinate grid to a map item in a print layout. "
            "interval_x/interval_y set grid spacing in map or grid CRS units.",
        )
        async def add_layout_grid(
            ctx: Context,
            layout_name: str,
            map_item_id: str | None = None,
            interval_x: float = 1.0,
            interval_y: float = 1.0,
            name: str = "Grid",
            show_annotations: bool = True,
            crs: str | None = None,
            instance: str | None = None,
        ) -> dict:
            v = self.validate(
                LayoutGridParams,
                layout_name=layout_name,
                map_item_id=map_item_id,
                interval_x=interval_x,
                interval_y=interval_y,
                name=name,
                show_annotations=show_annotations,
                crs=crs,
            )
            return await _send(
                "add_layout_grid", v.model_dump(exclude_none=True), instance=instance
            )

        @mcp.tool(
            title="Update Layout Item",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Move, resize, update text, or toggle visibility of an item in a print layout.",
        )
        async def update_layout_item(
            ctx: Context,
            layout_name: str,
            item_id: str,
            x: float | None = None,
            y: float | None = None,
            width: float | None = None,
            height: float | None = None,
            text: str | None = None,
            visible: bool | None = None,
            instance: str | None = None,
        ) -> dict:
            v = self.validate(
                UpdateLayoutItemParams,
                layout_name=layout_name,
                item_id=item_id,
                x=x,
                y=y,
                width=width,
                height=height,
                text=text,
                visible=visible,
            )
            return await _send(
                "update_layout_item", v.model_dump(exclude_none=True), instance=instance
            )

        @mcp.tool(
            title="Remove Layout Item",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Remove an item from a print layout by UUID or ID.",
        )
        async def remove_layout_item(
            ctx: Context,
            layout_name: str,
            item_id: str,
            instance: str | None = None,
        ) -> dict:
            v = self.validate(RemoveLayoutItemParams, layout_name=layout_name, item_id=item_id)
            if not await _confirm_destructive(
                ctx, f"Remove item '{v.item_id}' from layout '{v.layout_name}'?"
            ):
                return {"ok": False, "message": "Cancelled by user"}
            return await _send("remove_layout_item", v.model_dump(), instance=instance)

    def register(self) -> None:
        self._register_layout_core_tools()
        self._register_layout_map_and_text_tools()
        self._register_layout_graphic_and_table_tools()
        self._register_layout_item_management_tools()
        self._register_atlas_tools()
