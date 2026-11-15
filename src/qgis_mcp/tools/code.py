"""Code Execution tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.helpers import ToolError, checked_timeout
from qgis_mcp.tools.base import BaseToolset, Context


class CodeToolset(BaseToolset):
    """MCP toolset for executing PyQGIS snippets inside QGIS."""

    domain = "code"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        _confirm_destructive = self._confirm_destructive
        timeout_long = self.context.timeout_long
        code_failure_message = self.context.code_failure_message

        @mcp.tool(
            title="Execute Code",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Execute arbitrary PyQGIS code. Use for operations not covered by other tools. "
            "Has access to QgsProject, iface, and core QGIS classes. Returns stdout/stderr and elapsed "
            "seconds. timeout: seconds before the script is cancelled (default 55); a script that runs "
            "past it comes back with timed_out=True and the output printed so far, and its side effects "
            "stand. Raise timeout or split bulk work into several calls; QGIS is unresponsive while a "
            "script runs. A single blocking call (time.sleep, GDAL) cannot be interrupted before it returns. "
            "A script that raises or times out is a tool error carrying the traceback and output so far.",
        )
        async def execute_code(
            ctx: Context, code: str, timeout: int | None = None, instance: str | None = None
        ) -> dict:
            if not await _confirm_destructive(
                ctx, "Execute arbitrary PyQGIS code? This can modify your project and system."
            ):
                return {"ok": False, "message": "Cancelled by user"}
            await ctx.info("Executing PyQGIS code...")
            await ctx.report_progress(0, 100)
            params: dict[str, Any] = {"code": code}
            if timeout is None:
                socket_timeout = timeout_long
            else:
                params["timeout"] = checked_timeout(timeout)
                socket_timeout = timeout + 5
            result = await _send("execute_code", params, timeout=socket_timeout, instance=instance)
            await ctx.report_progress(100, 100)
            if failure := code_failure_message(result):
                raise ToolError(failure)
            return result
