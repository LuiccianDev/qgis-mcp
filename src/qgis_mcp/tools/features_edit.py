"""Feature Editing tools."""

from typing import Any

from mcp.types import ToolAnnotations

from qgis_mcp.tools.base import BaseToolset, Context


class FeatureEditToolset(BaseToolset):
    """MCP toolset for vector feature and schema editing."""

    domain = "features_edit"

    def _register_feature_mutation_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        _confirm_destructive = self._confirm_destructive

        @mcp.tool(
            title="Add Features",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Add features to a vector layer. Each feature: {attributes: {field: value}, "
            "geometry_wkt: 'POINT(1 2)'}. geometry_wkt is in the layer's CRS, or in crs when given "
            "(it is then reprojected). A geometry type the layer cannot hold is refused; invalid "
            "geometry or 2D on a Z layer comes back in warnings. Returns count of added features.",
        )
        async def add_features(
            ctx: Context,
            layer_id: str,
            features: list[dict],
            crs: str | None = None,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {"layer_id": layer_id, "features": features}
            if crs:
                params["crs"] = crs
            return await _send("add_features", params, instance=instance)

        @mcp.tool(
            title="Update Features",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Update feature attributes. updates: [{fid: 1, attributes: {field: value}}]. "
            "Returns count of updated features.",
        )
        async def update_features(
            ctx: Context,
            layer_id: str,
            updates: list[dict],
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "update_features", {"layer_id": layer_id, "updates": updates}, instance=instance
            )

        @mcp.tool(
            title="Delete Features",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Delete features by feature IDs or expression filter. "
            "Provide either fids (list of ints) or expression (string), not both. Returns requested "
            "and the measured deleted count.",
        )
        async def delete_features(
            ctx: Context,
            layer_id: str,
            fids: list[int] | None = None,
            expression: str | None = None,
            instance: str | None = None,
        ) -> dict:
            target = f"fids={fids}" if fids is not None else f"expression='{expression}'"
            if not await _confirm_destructive(
                ctx, f"Delete features from layer {layer_id} ({target})?"
            ):
                return {"ok": False, "message": "Cancelled by user"}
            params: dict[str, Any] = {"layer_id": layer_id}
            if fids is not None:
                params["fids"] = fids
            if expression:
                params["expression"] = expression
            return await _send("delete_features", params, instance=instance)

        @mcp.tool(
            title="Update Feature Geometry",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Replace feature geometries. updates: [{fid: 1, geometry_wkt: 'POINT(1 2)'}]. "
            "WKT must be in the layer's CRS. Inside an edit session the change is undoable; "
            "otherwise it is written straight to the data source.",
        )
        async def update_feature_geometry(
            ctx: Context,
            layer_id: str,
            updates: list[dict],
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "update_feature_geometry",
                {"layer_id": layer_id, "updates": updates},
                instance=instance,
            )

    def _register_field_schema_tools(self) -> None:
        mcp = self.mcp
        _send = self._send
        _confirm_destructive = self._confirm_destructive

        @mcp.tool(
            title="Add Field",
            description="Add a new field to a vector layer. field_type: 'string', 'int', 'double', 'bool', 'date', 'datetime'.",
        )
        async def add_field(
            ctx: Context,
            layer_id: str,
            field_name: str,
            field_type: str,
            length: int | None = None,
            precision: int | None = None,
            instance: str | None = None,
        ) -> dict:
            params: dict[str, Any] = {
                "layer_id": layer_id,
                "field_name": field_name,
                "field_type": field_type,
            }
            if length is not None:
                params["length"] = length
            if precision is not None:
                params["precision"] = precision
            return await _send("add_field", params, instance=instance)

        @mcp.tool(
            title="Delete Field",
            annotations=ToolAnnotations(destructiveHint=True),
            description="Delete a field from a vector layer.",
        )
        async def delete_field(
            ctx: Context,
            layer_id: str,
            field_name: str,
            instance: str | None = None,
        ) -> dict:
            if not await _confirm_destructive(
                ctx, f"Delete field '{field_name}' from layer {layer_id}?"
            ):
                return {"ok": False, "message": "Cancelled by user"}
            return await _send(
                "delete_field", {"layer_id": layer_id, "field_name": field_name}, instance=instance
            )

        @mcp.tool(
            title="Rename Field",
            description="Rename a field in a vector layer.",
        )
        async def rename_field(
            ctx: Context,
            layer_id: str,
            old_name: str,
            new_name: str,
            instance: str | None = None,
        ) -> dict:
            return await _send(
                "rename_field",
                {"layer_id": layer_id, "old_name": old_name, "new_name": new_name},
                instance=instance,
            )

    def register(self) -> None:
        self._register_feature_mutation_tools()
        self._register_field_schema_tools()
