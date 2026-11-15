"""Layer Tree tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class LayerTreeToolset(BaseToolset):
    """MCP toolset for inspecting and organizing the QGIS layer tree."""

    domain = "layertree"

    def register(self) -> None:
        mcp = self.mcp
        _send = self._send

        @mcp.tool(
            title="Get Layer Tree",
            annotations=ToolAnnotations(readOnlyHint=True),
            description="Get the full layer tree structure with groups and layers. "
            "Returns recursive tree with type, name, visibility, and children.",
            structured_output=True,
        )
        async def get_layer_tree(ctx: Context, instance: str | None = None) -> dict[str, Any]:
            return await _send("get_layer_tree", instance=instance)

        @mcp.tool(
            title="Create Layer Group",
            description="Create a new layer group in the layer tree. "
            "Optionally specify a parent group name.",
        )
        async def create_layer_group(
            ctx: Context,
            name: str,
            parent: str | None = None,
            instance: str | None = None,
        ) -> dict:
            params = {"name": name}
            if parent:
                params["parent"] = parent
            return await _send("create_layer_group", params, instance=instance)

        @mcp.tool(
            title="Move Layer to Group",
            description="Move a layer into a layer group by group name.",
        )
        async def move_layer_to_group(
            ctx: Context,
            layer_id: str,
            group_name: str,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "move_layer_to_group",
                {"layer_id": layer_id, "group_name": group_name},
                instance=instance,
            )

        @mcp.tool(
            title="Set Layer Order",
            annotations=ToolAnnotations(idempotentHint=True),
            description="Reorder layer tree nodes; tree order is draw order. layer_ids is the ordered "
            "list of layer ids from top (drawn last) to bottom; unlisted layers keep their slots. "
            "Clears any custom draw order (it freezes a snapshot list - layers added later would "
            "silently draw behind everything).",
        )
        async def set_layer_order(
            ctx: Context, layer_ids: list[str], instance: str | None = None
        ) -> dict:
            return await _send("set_layer_order", {"layer_ids": layer_ids}, instance=instance)
