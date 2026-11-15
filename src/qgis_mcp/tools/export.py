"""Export tools."""

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class ExportToolset(BaseToolset):
    """MCP toolset for exporting layers to disk."""

    domain = "export"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="Export Layer",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Export vector/raster to disk; format from output_path extension "
            "(.gpkg, .shp, .geojson, .tif, ...). target_crs (e.g. 'EPSG:4326') reprojects on export. "
            "filter_expression (vector only) exports a subset matching a QGIS expression.",
        )
        async def export_layer(
            ctx: Context,
            layer_id: str,
            output_path: str,
            target_crs: str | None = None,
            filter_expression: str | None = None,
            instance: str | None = None,
        ) -> dict:
            await ctx.info(f"Exporting layer to {output_path}")
            return await _send(
                "export_layer",
                {
                    "layer_id": layer_id,
                    "output_path": output_path,
                    "target_crs": target_crs,
                    "filter_expression": filter_expression,
                },
                timeout=timeout_long,
                instance=instance,
            )
