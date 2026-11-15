"""Settings tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class SettingsToolset(BaseToolset):
    """MCP toolset for reading and updating QGIS settings."""

    domain = "settings"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        _confirm_destructive = self._confirm_destructive

        @mcp.tool(
            title="Get Setting",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Read a QGIS setting by key path (e.g. 'qgis/sketching/sketching_enabled').",
            structured_output=True,
        )
        async def get_setting(
            ctx: Context, key: str, instance: str | None = None
        ) -> dict[str, Any]:
            return await _send("get_setting", {"key": key}, instance=instance)

        @mcp.tool(
            title="Set Setting",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Write a QGIS setting. Use with care - incorrect settings can affect QGIS behavior.",
        )
        async def set_setting(
            ctx: Context, key: str, value: str, instance: str | None = None
        ) -> dict:
            if not await _confirm_destructive(
                ctx, f"Set QGIS setting '{key}'? Incorrect settings can affect behavior."
            ):
                return {"ok": False, "message": "Cancelled by user"}
            return await _send("set_setting", {"key": key, "value": value}, instance=instance)
