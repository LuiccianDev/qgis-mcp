"""Plugin Management tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class PluginToolset(BaseToolset):
    """MCP toolset for listing, inspecting, and reloading QGIS plugins."""

    domain = "plugin"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="List Plugins",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List installed QGIS plugins with name, enabled status, and version. "
            "Set enabled_only=true to list only active plugins.",
            structured_output=True,
        )
        async def list_plugins(
            ctx: Context,
            enabled_only: bool = False,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send("list_plugins", {"enabled_only": enabled_only}, instance=instance)

        @mcp.tool(
            title="Get Plugin Info",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get detailed info for a specific plugin: name, enabled, version, description, author, path.",
            structured_output=True,
        )
        async def get_plugin_info(
            ctx: Context,
            plugin_name: str,
            instance: str | None = None,
        ) -> dict[str, Any]:
            return await _send("get_plugin_info", {"plugin_name": plugin_name}, instance=instance)

        @mcp.tool(
            title="Reload Plugin",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Reload a QGIS plugin by name. Cannot reload the MCP plugin itself. "
            "Useful during plugin development.",
        )
        async def reload_plugin(
            ctx: Context, plugin_name: str, instance: str | None = None
        ) -> dict:
            if not await self._confirm_destructive(ctx, f"Reload plugin '{plugin_name}'?"):
                return {"ok": False, "message": "Cancelled by user"}
            await ctx.info(f"Reloading plugin: {plugin_name}")
            return await _send("reload_plugin", {"plugin_name": plugin_name}, instance=instance)
