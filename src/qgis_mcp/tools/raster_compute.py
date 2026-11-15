"""Raster compute tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class RasterComputeToolset(BaseToolset):
    """MCP toolset for raster calculator, zonal statistics, and raster pixel sampling."""

    domain = "raster_compute"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="Raster Calculator",
            description="Band math via the QGIS raster calculator. Reference loaded raster layers "
            "in the expression as 'LayerName@band' (e.g. '(\"dem@1\" > 1000) * 1'). Writes a GeoTIFF "
            "to output_path. Output grid, extent and CRS taken from reference_layer (layer id or "
            "name), defaulting to the first loaded file-based raster.",
        )
        async def raster_calculator(
            ctx: Context,
            expression: str,
            output_path: str,
            reference_layer: str | None = None,
            instance: str | None = None,
        ) -> dict:
            await ctx.info("Computing raster expression...")
            return await _send(
                "raster_calculator",
                {
                    "expression": expression,
                    "output_path": output_path,
                    "reference_layer": reference_layer,
                },
                timeout=timeout_long,
                instance=instance,
            )

        @mcp.tool(
            title="Zonal Statistics",
            description="Per-polygon stats from a raster (native:zonalstatisticsfb). "
            "stats int codes: 0=count 1=sum 2=mean 3=median 4=stdev 5=min 6=max "
            "7=range 8=minority 9=majority 10=variety 11=variance (default [0,1,2]). New columns "
            "prefixed by 'prefix'. No output_path = in-memory layer.",
        )
        async def zonal_statistics(
            ctx: Context,
            polygon_layer: str,
            raster_layer: str,
            band: int = 1,
            prefix: str = "_",
            stats: list[int] | None = None,
            output_path: str | None = None,
            instance: str | None = None,
        ) -> dict:
            await ctx.info("Computing zonal statistics...")
            return await _send(
                "zonal_statistics",
                {
                    "polygon_layer": polygon_layer,
                    "raster_layer": raster_layer,
                    "band": band,
                    "prefix": prefix,
                    "stats": stats,
                    "output_path": output_path,
                },
                timeout=timeout_long,
                instance=instance,
            )

        @mcp.tool(
            title="Sample Raster Values",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Sample raster pixel values at points. 'points' is a list of [x, y] in crs "
            "when given (reprojected to the raster), else in the raster's CRS. Omit 'band' to sample "
            "all bands. A null value is nodata when outside_extent is false; outside_extent true "
            "means the point is off the raster (often a CRS mix-up); transform_failed marks a point "
            "the raster's CRS cannot express.",
        )
        async def sample_raster_values(
            ctx: Context,
            raster_layer: str,
            points: list[list[float]],
            band: int | None = None,
            crs: str | None = None,
            instance: str | None = None,
        ) -> dict[str, Any]:
            params: dict[str, Any] = {"raster_layer": raster_layer, "points": points, "band": band}
            if crs:
                params["crs"] = crs
            return await _send("sample_raster_values", params, instance=instance)
