"""Session checkpoints and replay tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class SessionToolset(BaseToolset):
    """MCP toolset for project checkpoints and replayable session export."""

    domain = "session"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        timeout_long = self.context.timeout_long

        @mcp.tool(
            title="Create Checkpoint",
            description="Snapshot the whole project (layers, styles, labels, layouts, map themes, "
            "variables, and the features of memory layers) so restore_checkpoint can return to it. "
            "Take one before a sequence of changes you may want to undo. The user's project file is "
            "not touched. Data in files and databases is not copied, and uncommitted edits are "
            "listed under 'uncommitted_edits' because the checkpoint does not hold them. The last 20 "
            "are kept, until the plugin's server stops.",
        )
        async def create_checkpoint(
            ctx: Context, name: str | None = None, instance: str | None = None
        ) -> dict:
            params = {"name": name} if name else {}
            return await _send("create_checkpoint", params, timeout=timeout_long, instance=instance)

        @mcp.tool(
            title="List Checkpoints",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="List the project checkpoints: id, name, creation time, layer count.",
            structured_output=True,
        )
        async def list_checkpoints(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("list_checkpoints", instance=instance)

        @mcp.tool(
            title="Restore Checkpoint",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Put the project back as it was at a checkpoint: every change since, and any "
            "uncommitted edit, is discarded. The project keeps its file name and is left unsaved. "
            "Memory layer features come back with new feature ids. Layers whose source is missing "
            "are kept as unavailable and listed in 'unavailable_layers'. "
            "export_session afterwards replays the restored state, not the undone steps.",
        )
        async def restore_checkpoint(
            ctx: Context, checkpoint_id: str, instance: str | None = None
        ) -> dict:
            return await _send(
                "restore_checkpoint",
                {"checkpoint_id": checkpoint_id},
                timeout=timeout_long,
                instance=instance,
            )

        @mcp.tool(
            title="Export Session Script",
            description="Every command that changed something in this QGIS since the plugin's server "
            "started (read-only calls left out), as a Python script that replays them from the QGIS "
            "Python console. Layer ids are remapped on replay. Returns the script, or writes it to "
            "'path' and returns the path. clear: start a new journal afterwards. Commands from every "
            "connected client are in it; a restore_checkpoint rewinds it.",
        )
        async def export_session(
            ctx: Context,
            path: str | None = None,
            clear: bool = False,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {}
            if path:
                params["path"] = path
            if clear:
                params["clear"] = True
            return await _send("export_session", params, instance=instance)
