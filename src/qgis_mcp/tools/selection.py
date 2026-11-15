"""Selection tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class SelectionToolset(BaseToolset):
    """MCP toolset for vector layer feature selection."""

    domain = "selection"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Select Features",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Select features in a layer by expression or feature IDs.",
        )
        async def select_features(
            ctx: Context,
            layer_id: str,
            expression: str | None = None,
            fids: list[int] | None = None,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {"layer_id": layer_id}
            if expression:
                params["expression"] = expression
            if fids is not None:
                params["fids"] = fids
            return await _send("select_features", params, instance=instance)

        @mcp.tool(
            title="Get Selection",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get the current selection for a layer. Returns feature IDs and count.",
            structured_output=True,
        )
        async def get_selection(
            ctx: Context, layer_id: str, instance: str | None = None
        ) -> dict[str, Any]:
            return await _send("get_selection", {"layer_id": layer_id}, instance=instance)

        @mcp.tool(
            title="Clear Selection",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Clear the selection on a layer.",
        )
        async def clear_selection(ctx: Context, layer_id: str, instance: str | None = None) -> dict:
            return await _send("clear_selection", {"layer_id": layer_id}, instance=instance)
