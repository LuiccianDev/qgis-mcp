"""Canvas tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.helpers import make_image_response
from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import CanvasExtentParams, Screenshot3DParams


class CanvasToolset(BaseToolset):
    """MCP toolset for map canvas extent and screenshot operations."""

    domain = "canvas"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Get Canvas Extent",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get the current map canvas extent and CRS.",
            structured_output=True,
        )
        async def get_canvas_extent(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("get_canvas_extent", instance=instance)

        @mcp.tool(
            title="Set Canvas Extent",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Set the map canvas extent. Coordinates should be in the specified CRS (default: project CRS).",
        )
        async def set_canvas_extent(
            ctx: Context,
            xmin: float,
            ymin: float,
            xmax: float,
            ymax: float,
            crs: str | None = None,
            instance: str | None = None,
        ) -> dict:
            validated = self.validate(
                CanvasExtentParams, xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax
            )
            params: dict[str, Any] = {
                "xmin": validated.xmin,
                "ymin": validated.ymin,
                "xmax": validated.xmax,
                "ymax": validated.ymax,
            }
            if crs:
                params["crs"] = crs
            return await _send("set_canvas_extent", params, instance=instance)

        @mcp.tool(
            title="Get Canvas Screenshot",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Grab a fast screenshot of the current map canvas widget (no re-render). "
            "Returns the image inline. Much faster than render_map.",
        )
        async def get_canvas_screenshot(ctx: Context, instance: str | None = None) -> list:
            result = await _send("get_canvas_screenshot", instance=instance)
            return make_image_response(result)

        @mcp.tool(
            title="Get 3D Screenshot",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Capture an OPEN 3D Map View as an inline image. Reuses the open view's "
            "scene + camera, rendered via a print-layout 3D map item (the 2D get_canvas_screenshot "
            "cannot capture the OpenGL 3D view). Requires a 3D map view to be open in QGIS "
            "(View > 3D Map Views > New 3D Map View). view_index selects which view when several "
            "are open; dpi controls output resolution. Optional camera overrides (applied to the "
            "capture only, leaving the live view unchanged): pitch (0 = straight down/top-down, "
            "90 = horizontal/edge-on; ~45 = balanced oblique), heading (compass degrees), "
            "distance (metres).",
        )
        async def get_3d_screenshot(
            ctx: Context,
            view_index: int = 0,
            dpi: int = 96,
            pitch: float | None = None,
            distance: float | None = None,
            heading: float | None = None,
            instance: str | None = None,
        ) -> list:
            validated = self.validate(
                Screenshot3DParams,
                view_index=view_index,
                dpi=dpi,
                pitch=pitch,
                distance=distance,
                heading=heading,
            )
            params: dict[str, Any] = {
                "view_index": validated.view_index,
                "dpi": validated.dpi,
            }
            if validated.pitch is not None:
                params["pitch"] = validated.pitch
            if validated.distance is not None:
                params["distance"] = validated.distance
            if validated.heading is not None:
                params["heading"] = validated.heading
            result = await _send("get_3d_screenshot", params, instance=instance)
            return make_image_response(result)
