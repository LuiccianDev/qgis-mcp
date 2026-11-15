"""Message Log and Debugging tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import MessageLogParams


class DebugToolset(BaseToolset):
    """MCP toolset for inspecting QGIS message logs."""

    domain = "debug"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Get Message Log",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get QGIS message log entries. Filter by level ('info', 'warning', 'critical', "
            "'success', 'none') "
            "and/or tag (e.g. 'QGIS MCP'). Returns newest first.",
            structured_output=True,
        )
        async def get_message_log(
            ctx: Context,
            level: str | None = None,
            tag: str | None = None,
            limit: int = 100,
            instance: str | None = None,
        ) -> dict[str, Any]:
            validated = self.validate(MessageLogParams, limit=limit)
            params: dict[str, Any] = {"limit": validated.limit}
            if level:
                params["level"] = level
            if tag:
                params["tag"] = tag
            return await _send("get_message_log", params, instance=instance)
