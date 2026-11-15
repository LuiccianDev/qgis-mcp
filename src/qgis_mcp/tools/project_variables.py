"""Project Variables tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class ProjectVariablesToolset(BaseToolset):
    """MCP toolset for reading and writing QGIS project variables."""

    domain = "project_variables"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Get Project Variables",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get all project-level variables (key-value pairs set in Project Properties).",
            structured_output=True,
        )
        async def get_project_variables(
            ctx: Context, instance: str | None = None
        ) -> dict[str, Any]:
            return await _send("get_project_variables", instance=instance)

        @mcp.tool(
            title="Set Project Variable",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Set a project-level variable. Variables are accessible in expressions as @key.",
        )
        async def set_project_variable(
            ctx: Context,
            key: str,
            value: str,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "set_project_variable", {"key": key, "value": value}, instance=instance
            )
