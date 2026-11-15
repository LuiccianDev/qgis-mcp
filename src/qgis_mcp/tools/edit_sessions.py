"""Edit Sessions tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context
from qgis_mcp.validation import UndoRedoParams


class EditSessionToolset(BaseToolset):
    """MCP toolset for vector layer edit sessions, buffer status, and undo/redo."""

    domain = "edit_sessions"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send
        _confirm_destructive = self._confirm_destructive

        @mcp.tool(
            title="Start Editing",
            description="Open an edit session on a vector layer. Subsequent add/update/delete calls go to "
            "the undoable edit buffer instead of the data source, until commit_edits or rollback_edits.",
        )
        async def start_editing(ctx: Context, layer_id: str, instance: str | None = None) -> dict:
            return await _send("start_editing", {"layer_id": layer_id}, instance=instance)

        @mcp.tool(
            title="Commit Edits",
            description="Commit the layer's edit buffer to the data source and close the edit session.",
        )
        async def commit_edits(ctx: Context, layer_id: str, instance: str | None = None) -> dict:
            await ctx.info(f"Committing edits on layer {layer_id}")
            return await _send("commit_edits", {"layer_id": layer_id}, instance=instance)

        @mcp.tool(
            title="Rollback Edits",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Discard every uncommitted change on a layer and close the edit session.",
        )
        async def rollback_edits(ctx: Context, layer_id: str, instance: str | None = None) -> dict:
            if not await _confirm_destructive(
                ctx, f"Discard all uncommitted edits on layer {layer_id}? This cannot be undone."
            ):
                return {"ok": False, "message": "Cancelled by user"}
            return await _send("rollback_edits", {"layer_id": layer_id}, instance=instance)

        @mcp.tool(
            title="Get Edit Status",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Edit state of a layer: editable, modified, undo/redo availability, and the "
            "counts of pending added/deleted/changed features.",
            structured_output=True,
        )
        async def get_edit_status(
            ctx: Context, layer_id: str, instance: str | None = None
        ) -> dict[str, Any]:
            return await _send("get_edit_status", {"layer_id": layer_id}, instance=instance)

        @mcp.tool(
            title="Undo Edits",
            description="Undo the last edit operations on a layer (its own undo stack). "
            "Returns how many steps were actually undone.",
        )
        async def undo_edits(
            ctx: Context, layer_id: str, steps: int = 1, instance: str | None = None
        ) -> dict:
            validated = self.validate(UndoRedoParams, layer_id=layer_id, steps=steps)
            return await _send(
                "undo_edits",
                {"layer_id": validated.layer_id, "steps": validated.steps},
                instance=instance,
            )

        @mcp.tool(
            title="Redo Edits",
            description="Redo previously undone edit operations on a layer.",
        )
        async def redo_edits(
            ctx: Context, layer_id: str, steps: int = 1, instance: str | None = None
        ) -> dict:
            validated = self.validate(UndoRedoParams, layer_id=layer_id, steps=steps)
            return await _send(
                "redo_edits",
                {"layer_id": validated.layer_id, "steps": validated.steps},
                instance=instance,
            )
