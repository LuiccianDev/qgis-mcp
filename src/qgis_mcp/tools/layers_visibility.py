"""Layer Visibility and Navigation tools."""

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class LayerVisibilityToolset(BaseToolset):
    """MCP toolset for layer visibility toggling and zooming."""

    domain = "layers_visibility"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Set Layer Visibility",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Set a layer's visibility in the layer tree (show/hide on map).",
        )
        async def set_layer_visibility(
            ctx: Context,
            layer_id: str,
            visible: bool,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "set_layer_visibility",
                {"layer_id": layer_id, "visible": visible},
                instance=instance,
            )

        @mcp.tool(
            title="Zoom to Layer",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Zoom the map canvas to the full extent of the specified layer.",
        )
        async def zoom_to_layer(ctx: Context, layer_id: str, instance: str | None = None) -> dict:
            return await _send("zoom_to_layer", {"layer_id": layer_id}, instance=instance)
