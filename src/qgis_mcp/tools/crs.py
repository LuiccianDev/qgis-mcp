"""CRS Transformation tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import TransformCoordinatesParams


class CrsToolset(BaseToolset):
    """MCP toolset for coordinate reference system transformations."""

    domain = "crs"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Transform Coordinates",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Transform coordinates between CRS. Accepts a point {x, y}, "
            "a point list [{x, y}, ...], or a bbox {xmin, ymin, xmax, ymax}. "
            "Returns the same format. x is always longitude/easting and y latitude/northing, "
            "including for EPSG:4326. A bbox that crosses the antimeridian comes back with "
            "xmin > xmax and crosses_antimeridian: true.",
            structured_output=True,
        )
        async def transform_coordinates(
            ctx: Context,
            source_crs: str,
            target_crs: str,
            point: dict | None = None,
            points: list[dict] | None = None,
            bbox: dict | None = None,
            instance: str | None = None,
        ) -> dict[str, Any]:
            validated = self.validate(
                TransformCoordinatesParams,
                source_crs=source_crs,
                target_crs=target_crs,
                point=point,
                points=points,
                bbox=bbox,
            )
            params: dict[str, Any] = {
                "source_crs": validated.source_crs,
                "target_crs": validated.target_crs,
            }
            if point:
                params["point"] = point
            if points:
                params["points"] = points
            if bbox:
                params["bbox"] = bbox
            return await _send("transform_coordinates", params, instance=instance)
