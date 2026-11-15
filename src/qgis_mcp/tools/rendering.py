"""Rendering tools."""

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import RenderMapParams


class RenderingToolset(BaseToolset):
    """MCP toolset for map image rendering."""

    domain = "rendering"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long
        make_render_response = self.context.make_render_response

        @mcp.tool(
            title="Render Map",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Render the current map canvas to an image. Returns the image inline so you can see it. "
            "Optionally saves to a file path on disk.",
        )
        async def render_map(
            ctx: Context,
            width: int = 800,
            height: int = 600,
            path: str | None = None,
            instance: str | None = None,
        ) -> list:
            validated = self.validate(RenderMapParams, width=width, height=height)
            await ctx.info("Rendering map...")
            await ctx.report_progress(0, 100)
            params: dict = {"width": validated.width, "height": validated.height}
            if path:
                params["path"] = path
            result = await _send(
                "render_map_base64", params, timeout=timeout_long, instance=instance
            )
            await ctx.report_progress(100, 100)
            return make_render_response(result, validated.width, validated.height, path)
