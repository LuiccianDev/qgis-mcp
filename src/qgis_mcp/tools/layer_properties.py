"""Layer Properties tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class LayerPropertiesToolset(BaseToolset):
    """MCP toolset for layer properties and spatial extents."""

    domain = "layer_properties"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Set Layer Property",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Set a layer property. Supported properties: opacity (0.0-1.0), name (string), "
            "min_scale, max_scale (float), scale_visibility (bool).",
        )
        async def set_layer_property(
            ctx: Context,
            layer_id: str,
            property: str,
            value: str,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "set_layer_property",
                {"layer_id": layer_id, "property": property, "value": value},
                instance=instance,
            )

        @mcp.tool(
            title="Get Layer Extent",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get the spatial extent (bounding box) and CRS of a layer.",
            structured_output=True,
        )
        async def get_layer_extent(
            ctx: Context,
            layer_id: str,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send("get_layer_extent", {"layer_id": layer_id}, instance=instance)
