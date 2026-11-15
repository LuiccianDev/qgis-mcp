"""Project Management tools."""

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class ProjectToolset(BaseToolset):
    """MCP toolset for loading, creating, and saving QGIS projects."""

    domain = "project"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        make_project_response = self.context.make_project_response

        @mcp.tool(
            title="Load Project",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Load a QGIS project from a .qgs/.qgz file path. Replaces the open project; "
            "unsaved changes to it are lost. Layers whose source is missing are kept as unavailable "
            "and listed in 'unavailable_layers'.",
        )
        async def load_project(ctx: Context, path: str, instance: str | None = None) -> list:
            await ctx.info(f"Loading project: {path}")
            result = await _send("load_project", {"path": path}, instance=instance)
            return make_project_response(result)

        @mcp.tool(
            title="Create New Project",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Create a new empty QGIS project and save it to the given path. Replaces the "
            "open project; unsaved changes to it are lost.",
        )
        async def create_new_project(ctx: Context, path: str, instance: str | None = None) -> list:
            result = await _send("create_new_project", {"path": path}, instance=instance)
            return make_project_response(result)

        @mcp.tool(
            title="Save Project",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Save the current project. Optionally specify a new path.",
        )
        async def save_project(
            ctx: Context, path: str | None = None, instance: str | None = None
        ) -> dict:
            params = {}
            if path:
                params["path"] = path
            return await _send("save_project", params, instance=instance)
