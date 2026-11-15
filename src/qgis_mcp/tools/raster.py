"""Raster tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class RasterToolset(BaseToolset):
    """MCP toolset for raster layer metadata inspection."""

    domain = "raster"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Get Raster Info",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get raster layer info: band count, dimensions, CRS, extent, per-band statistics, nodata values.",
            structured_output=True,
        )
        async def get_raster_info(
            ctx: Context,
            layer_id: str,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send("get_raster_info", {"layer_id": layer_id}, instance=instance)
